"""Vistas del módulo Caja (cobro + facturación).

Flujo: el empleado toma el pedido en el POS (queda pendiente e imprime
el ticket). El cliente se acerca a Caja con el ticket, la cajera busca
el pedido, elige Consumidor Final o carga los datos del receptor,
registra el pago (con vuelto si es efectivo) y al completar se emite la
factura electrónica.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Case, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from app.orders.models import Cliente, Order
from app.orders.validators import (
    errores_monto,
    normalizar_nombre,
    validar_identificacion,
)
from app.users.decorators import EmpleadoRequiredMixin, empleado_required

from app.facturacion.sri.emision import EmisorInvalido, emitir_factura

METODO_PAGO_VALIDOS = {k for k, _ in Order.METODO_CHOICES}
TIPOS_IDENTIFICACION_VALIDOS = {k for k, _ in Order.TIPO_IDENTIFICACION_CHOICES}
MONTO_MAX_INT = 10  # max_digits=12 en el modelo -> 10 enteros + 2 decimales

IDENTIFICACION_CONSUMIDOR = '9999999999999'


def _pedidos():
    return (
        Order.objects.select_related('vendedor')
        .prefetch_related('items')
    )


class CajaIndexView(EmpleadoRequiredMixin, TemplateView):
    """Búsqueda por número de ticket y listado de todos los pedidos.

    Se muestran todos los pedidos (pendientes, cobrados y cancelados)
    con su estado; la búsqueda por número encuentra pedidos en cualquier
    estado (solo redirige al formulario de cobro si está pendiente).
    """

    template_name = 'caja/index.html'

    def get(self, request, *args, **kwargs):
        q = request.GET.get('q', '').strip()
        if q:
            pedido = _pedidos().filter(numero__icontains=q).first()
            if pedido:
                if pedido.estado == Order.ESTADO_PENDIENTE:
                    return redirect('caja:caja_detalle', pk=pedido.pk)
                if pedido.estado == Order.ESTADO_COMPLETADO:
                    messages.info(
                        request,
                        f'El pedido {pedido.numero} ya fue cobrado '
                        f'({pedido.get_metodo_pago_display()}).',
                    )
                else:
                    messages.info(
                        request, f'El pedido {pedido.numero} fue cancelado.',
                    )
                return redirect('caja:index')
            messages.info(
                request,
                f'No se encontró ningún pedido con "{q}".',
            )
            return redirect('caja:index')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pedidos = _pedidos().order_by('-creado')
        ctx['pedidos'] = pedidos
        ctx['n_pendientes'] = sum(1 for p in pedidos if p.estado == Order.ESTADO_PENDIENTE)
        ctx['n_cobrados'] = sum(1 for p in pedidos if p.estado == Order.ESTADO_COMPLETADO)
        ctx['n_cancelados'] = sum(1 for p in pedidos if p.estado == Order.ESTADO_CANCELADO)
        return ctx


class CajaDetalleView(EmpleadoRequiredMixin, DetailView):
    """Detalle del pedido a cobrar, con el formulario de pago y factura.

    La cajera puede procesar pedidos de cualquier vendedor (el cliente
    llega a caja con el ticket, no importa quién tomó el pedido).
    """

    model = Order
    template_name = 'caja/detalle.html'
    context_object_name = 'pedido'

    def get_queryset(self):
        return (
            Order.objects.filter(estado=Order.ESTADO_PENDIENTE)
            .select_related('vendedor')
            .prefetch_related('items__producto')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['metodos_pago'] = Order.METODO_CHOICES
        ctx['tipos_identificacion'] = Order.TIPO_IDENTIFICACION_CHOICES
        return ctx


@empleado_required
def caja_ticket(request, pk):
    """Ticket imprimible del pedido (visible para cualquier empleado)."""
    pedido = get_object_or_404(
        Order.objects.select_related('vendedor')
        .prefetch_related('items__producto'),
        pk=pk,
    )
    iva_pct = int(round(float(pedido.iva_alicuota) * 100))
    return render(request, 'orders/ticket.html', {'pedido': pedido, 'iva_pct': iva_pct})


@empleado_required
@require_POST
def caja_completar(request, pk):
    """Cobra el pedido, carga los datos del receptor y emite la factura."""
    pedido = get_object_or_404(
        Order.objects.filter(estado=Order.ESTADO_PENDIENTE)
        .select_related('vendedor')
        .prefetch_related('items__producto'),
        pk=pk,
    )
    data = request.POST
    errores = []

    metodo = (data.get('metodo_pago') or '').strip() or Order.METODO_EFECTIVO
    if metodo not in METODO_PAGO_VALIDOS:
        errores.append('Método de pago inválido.')

    tipo = (data.get('tipo_identificacion') or '').strip() or '07'
    if tipo not in TIPOS_IDENTIFICACION_VALIDOS:
        errores.append('Tipo de identificación inválido.')

    nombres = normalizar_nombre(data.get('nombres'))[:60]
    apellidos = normalizar_nombre(data.get('apellidos'))[:60]
    razon_social = normalizar_nombre(data.get('razon_social'))[:120]
    identificacion = (data.get('identificacion') or '').strip()
    direccion = (data.get('direccion') or '').strip()[:300]
    email = (data.get('email') or '').strip()[:254]
    telefono = (data.get('telefono') or '').strip()[:30]

    recibido = None
    if metodo == Order.METODO_EFECTIVO:
        try:
            recibido = Decimal(str(data.get('recibido') or '0'))
        except InvalidOperation:
            errores.append('Ingresá un monto recibido válido.')
        else:
            errores.extend(errores_monto(recibido, max_int=MONTO_MAX_INT))
            if recibido < pedido.total:
                errores.append(
                    f'El monto recibido (${recibido}) no cubre el total '
                    f'(${pedido.total}).'
                )

    # Datos del receptor según el tipo de identificación
    if tipo == '07':
        cliente = 'CONSUMIDOR FINAL'
        identificacion = IDENTIFICACION_CONSUMIDOR
        nombres = apellidos = razon_social = ''
    elif tipo == '04':
        # Personas jurídicas: solo razón social (no aplican nombres/apellidos)
        if not razon_social:
            errores.append('La razón social del cliente es obligatoria.')
        cliente = razon_social
        nombres = apellidos = ''
        errores.extend(validar_identificacion(tipo, identificacion))
    else:
        if not nombres or not apellidos:
            errores.append('Debe ingresar los nombres y apellidos del cliente.')
        cliente = f'{nombres} {apellidos}'.strip()[:120]
        razon_social = ''
        errores.extend(validar_identificacion(tipo, identificacion))

    if email:
        try:
            validate_email(email)
        except ValidationError:
            errores.append('El email es inválido.')

    if errores:
        return render(request, 'caja/detalle.html', {
            'pedido': pedido,
            'metodos_pago': Order.METODO_CHOICES,
            'tipos_identificacion': Order.TIPO_IDENTIFICACION_CHOICES,
            'errores': errores,
            'form_data': {
                'metodo_pago': metodo,
                'tipo_identificacion': tipo,
                'nombres': data.get('nombres', ''),
                'apellidos': data.get('apellidos', ''),
                'razon_social': data.get('razon_social', ''),
                'identificacion': data.get('identificacion', ''),
                'direccion': data.get('direccion', ''),
                'email': data.get('email', ''),
                'telefono': data.get('telefono', ''),
                'recibido': data.get('recibido', ''),
            },
        })

    with transaction.atomic():
        pedido.cliente = cliente
        pedido.nombres = nombres
        pedido.apellidos = apellidos
        pedido.tipo_identificacion = tipo
        pedido.identificacion = identificacion
        pedido.direccion = direccion
        pedido.email = email
        pedido.telefono = telefono
        pedido.metodo_pago = metodo
        pedido.save(update_fields=[
            'cliente', 'nombres', 'apellidos', 'tipo_identificacion',
            'identificacion', 'direccion', 'email', 'telefono',
            'metodo_pago', 'actualizado',
        ])
        pedido.completar(usuario=request.user)
        _guardar_cliente(pedido)

    vuelto = None
    if metodo == Order.METODO_EFECTIVO and recibido is not None:
        vuelto = (recibido - pedido.total).quantize(Decimal('0.01'))

    try:
        comp = emitir_factura(pedido)
        msg = f'Cobrado. Factura {comp.numero}: {comp.get_estado_display()}.'
        if vuelto is not None:
            msg += f' Vuelto: ${vuelto}.'
        messages.success(request, format_html(
            '{} <a href="{}" target="_blank" class="alert-link">'
            '<i class="fas fa-print"></i> Imprimir factura</a>',
            msg, reverse('facturacion:comprobante_pdf', args=[comp.pk]),
        ))
    except EmisorInvalido as exc:
        msg = f'Cobrado, pero la factura no pudo emitirse: {exc}'
        if vuelto is not None:
            msg += f' Vuelto: ${vuelto}.'
        messages.warning(request, msg)
    except Exception:  # noqa: BLE001 — el cobro no se pierde por un fallo de emisión
        msg = 'Cobrado, pero la factura quedó pendiente de emisión (revisá Facturación).'
        if vuelto is not None:
            msg += f' Vuelto: ${vuelto}.'
        messages.warning(request, msg)
    return redirect('caja:index')


def _guardar_cliente(pedido):
    """Guarda o actualiza la ficha del cliente habitual tras un cobro.

    Nunca guarda Consumidor Final. Solo se sobrescriben los campos que
    vengan con datos: una dirección vacía en una venta no borra la
    dirección guardada en la ficha.
    """
    if pedido.tipo_identificacion == '07' or not pedido.identificacion:
        return
    defaults = {}
    if pedido.cliente:
        defaults['nombre'] = pedido.cliente
    if pedido.nombres:
        defaults['nombres'] = pedido.nombres
    if pedido.apellidos:
        defaults['apellidos'] = pedido.apellidos
    if pedido.direccion:
        defaults['direccion'] = pedido.direccion
    if pedido.email:
        defaults['email'] = pedido.email
    if pedido.telefono:
        defaults['telefono'] = pedido.telefono
    if defaults:
        Cliente.objects.update_or_create(
            tipo_identificacion=pedido.tipo_identificacion,
            identificacion=pedido.identificacion,
            defaults=defaults,
        )


@empleado_required
def clientes_buscar(request):
    """Busca clientes por número de identificación (cédula/RUC/pasaporte).

    La identificación es única por persona, por eso es el criterio de
    búsqueda: coincidencia exacta primero y, si no, parcial mientras se
    tipea. El nombre se incluye solo para confirmar a quién corresponde.
    """
    q = (request.GET.get('q') or '').strip()
    clientes = Cliente.objects.exclude(tipo_identificacion='07')
    if q:
        clientes = (
            clientes.filter(identificacion__icontains=q)
            .order_by(
                Case(When(identificacion=q, then=0), default=1),
                'identificacion',
            )[:15]
        )
    else:
        clientes = clientes.none()
    return JsonResponse({
        'clientes': [
            {
                'id': c.pk,
                'nombre': c.nombre,
                'nombres': c.nombres or '',
                'apellidos': c.apellidos or '',
                'tipo_identificacion': c.tipo_identificacion,
                'identificacion': c.identificacion,
                'direccion': c.direccion,
                'email': c.email or '',
                'telefono': c.telefono,
            }
            for c in clientes
        ],
    })
