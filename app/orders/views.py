"""Vistas del módulo de pedidos."""
import json
from datetime import date as date_cls
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from app.products.models import Category, Product
from app.users.decorators import EmpleadoRequiredMixin

from .forms import OrderEditForm
from .models import Order, OrderItem
from .validators import errores_monto

MONTO_MAX_INT = 10  # max_digits=12 en el modelo -> 10 enteros + 2 decimales


def _pedidos_visibles(user):
    """Pedidos que puede ver/operar un usuario.

    Admins y superuser ven todos; empleados solo los suyos.
    """
    qs = Order.objects.all()
    profile = getattr(user, 'profile', None)
    if not (user.is_superuser or (profile and profile.es_admin)):
        qs = qs.filter(vendedor=user)
    return qs


# ---------- POS (punto de venta) ----------

class POSView(EmpleadoRequiredMixin, TemplateView):
    """Interfaz principal del punto de venta."""

    template_name = 'orders/pos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        categorias = Category.objects.filter(activa=True).order_by('orden', 'nombre')
        productos = (
            Product.objects.filter(activo=True)
            .select_related('categoria')
            .order_by('categoria__orden', 'nombre')
        )
        ctx['categorias'] = categorias
        ctx['productos'] = productos
        ctx['productos_json'] = [
            {
                'id': p.id,
                'nombre': p.nombre,
                'precio': str(p.precio),
                'categoria_id': p.categoria_id,
                'descripcion': p.descripcion or '',
            }
            for p in productos
        ]
        return ctx


MAX_CANTIDAD_POS = Decimal('999')


@login_required
@require_POST
def pos_crear_pedido(request):
    """Crea un pedido PENDIENTE desde el POS via JSON.

    El POS solo toma el pedido e imprime el ticket; el cobro y la
    factura se hacen en el módulo Caja.

    Valida cada ítem: producto activo existente, cantidad entera positiva
    entre 1 y MAX_CANTIDAD_POS. Si algún ítem falla, se rechaza todo el
    pedido (no se crean filas parciales) y se devuelve un error claro.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'error': 'JSON inválido'}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({'ok': False, 'error': 'Formato inválido.'}, status=400)

    # Usuarios desactivados no pueden cargar pedidos
    if not request.user.is_active:
        return JsonResponse({'ok': False, 'error': 'Tu cuenta está inactiva.'}, status=403)

    items = data.get('items') or []
    if not isinstance(items, list) or not items:
        return JsonResponse({'ok': False, 'error': 'Agregá al menos un producto.'}, status=400)

    notas = (data.get('notas') or '').strip()

    try:
        descuento = Decimal(str(data.get('descuento') or '0'))
    except InvalidOperation:
        return JsonResponse({'ok': False, 'error': 'Descuento inválido.'}, status=400)
    errores_desc = errores_monto(descuento, max_int=MONTO_MAX_INT)
    if errores_desc:
        return JsonResponse({'ok': False, 'error': errores_desc[0]}, status=400)

    # Validamos TODOS los items antes de tocar la base
    items_validos = []
    subtotal_esperado = Decimal('0.00')
    for idx, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            return JsonResponse({'ok': False, 'error': f'Ítem #{idx} inválido.'}, status=400)
        producto_id = it.get('producto_id')
        try:
            producto = Product.objects.get(pk=producto_id, activo=True)
        except (Product.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': f'Producto no encontrado en el ítem #{idx}.'}, status=400)
        try:
            cantidad = Decimal(str(it.get('cantidad', 1)))
        except (InvalidOperation, TypeError):
            return JsonResponse({'ok': False, 'error': f'Cantidad inválida en "{producto.nombre}".'}, status=400)
        if cantidad <= 0:
            return JsonResponse({'ok': False, 'error': f'La cantidad de "{producto.nombre}" debe ser mayor a cero.'}, status=400)
        if cantidad > MAX_CANTIDAD_POS:
            return JsonResponse({'ok': False, 'error': f'La cantidad de "{producto.nombre}" supera el máximo ({MAX_CANTIDAD_POS}).'}, status=400)
        nota = str(it.get('nota', ''))[:200]
        items_validos.append((producto, cantidad, nota))
        subtotal_esperado += (producto.precio * cantidad)

    # El descuento no puede superar el subtotal (mismo criterio que la edición)
    if descuento > subtotal_esperado:
        return JsonResponse({
            'ok': False,
            'error': f'El descuento (${descuento}) no puede ser mayor al subtotal (${subtotal_esperado}).',
        }, status=400)

    with transaction.atomic():
        pedido = Order.objects.create(
            vendedor=request.user,
            descuento=descuento,
            notas=notas,
        )
        for producto, cantidad, nota in items_validos:
            OrderItem.objects.create(
                pedido=pedido,
                producto=producto,
                cantidad=cantidad,
                precio_unitario=producto.precio,
                nota=nota,
            )
        pedido.recalcular_totales()

    return JsonResponse({
        'ok': True,
        'pedido_id': pedido.pk,
        'numero': pedido.numero,
        'total': str(pedido.total.quantize(Decimal('0.01'))),
        'ticket_url': f'/pedidos/{pedido.pk}/ticket/?auto=1',
    })


def _parsear_fecha(valor):
    """Convierte 'AAAA-MM-DD' a date; devuelve None si el formato es inválido."""
    if not valor:
        return None
    try:
        return date_cls.fromisoformat(valor.strip())
    except (ValueError, TypeError):
        return None


# ---------- Listado y detalle ----------

class OrderListView(EmpleadoRequiredMixin, ListView):
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'pedidos'
    paginate_by = 8

    def get_queryset(self):
        qs = _pedidos_visibles(self.request.user).select_related('vendedor').order_by('-creado')

        q = self.request.GET.get('q', '').strip()
        estado = self.request.GET.get('estado', '').strip()
        desde = self.request.GET.get('desde', '').strip()
        hasta = self.request.GET.get('hasta', '').strip()
        if q:
            qs = qs.filter(
                Q(numero__icontains=q) |
                Q(cliente__icontains=q) |
                Q(notas__icontains=q)
            )
        if estado:
            qs = qs.filter(estado=estado)
        # Fechas inválidas se ignoran (no rompen la búsqueda con 500)
        fecha_desde = _parsear_fecha(desde)
        fecha_hasta = _parsear_fecha(hasta)
        if fecha_desde:
            qs = qs.filter(creado__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(creado__date__lte=fecha_hasta)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'q': self.request.GET.get('q', ''),
            'estado': self.request.GET.get('estado', ''),
            'desde': self.request.GET.get('desde', ''),
            'hasta': self.request.GET.get('hasta', ''),
            'estados': Order.ESTADO_CHOICES,
        })
        return ctx


class OrderDetailView(EmpleadoRequiredMixin, DetailView):
    model = Order
    template_name = 'orders/order_detail.html'
    context_object_name = 'pedido'

    def get_queryset(self):
        # Empleados solo ven sus propios pedidos
        return _pedidos_visibles(self.request.user).select_related(
            'vendedor'
        ).prefetch_related('items__producto')


class OrderUpdateView(EmpleadoRequiredMixin, UpdateView):
    model = Order
    form_class = OrderEditForm
    template_name = 'orders/order_edit.html'

    def get_queryset(self):
        return _pedidos_visibles(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        pedido = self.get_object()
        # Solo se editan pedidos pendientes (integridad contable)
        if pedido.estado != Order.ESTADO_PENDIENTE:
            messages.error(
                request,
                f'Solo se pueden editar pedidos pendientes ("{pedido.numero}" '
                f'está {pedido.get_estado_display().lower()}).',
            )
            return redirect(pedido)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return self.object.get_absolute_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.recalcular_totales()
        messages.success(self.request, 'Pedido actualizado.')
        return response


@login_required
def order_ticket(request, pk):
    """Vista del ticket imprimible (solo usuarios autenticados, cada uno sus pedidos)."""
    pedido = get_object_or_404(
        _pedidos_visibles(request.user).select_related('vendedor')
        .prefetch_related('items__producto'),
        pk=pk,
    )
    iva_pct = int(round(float(pedido.iva_alicuota) * 100))
    return render(
        request,
        'orders/ticket.html',
        {'pedido': pedido, 'iva_pct': iva_pct},
    )


@login_required
@require_POST
def order_cancelar(request, pk):
    pedido = get_object_or_404(_pedidos_visibles(request.user), pk=pk)
    if pedido.estado != Order.ESTADO_PENDIENTE:
        messages.error(
            request,
            f'Solo se pueden cancelar pedidos pendientes ("{pedido.numero}" '
            f'está {pedido.get_estado_display().lower()}).',
        )
        return redirect(pedido)
    pedido.cancelar()
    messages.warning(request, f'Pedido {pedido.numero} cancelado.')
    return redirect(pedido)
