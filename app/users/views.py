"""Vistas de la app de usuarios."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView, DetailView, FormView, ListView, TemplateView, UpdateView,
)

from .decorators import AdminRequiredMixin, _es_superowner
from .forms import EmpleadoCreateForm, EmpleadoEditForm, StyledAuthenticationForm
from .models import Profile


# ──────────────────────────────────────────────
# Búsqueda global
# ──────────────────────────────────────────────

class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = 'users/search.html'

    def get_context_data(self, **kwargs):
        from app.products.models import Product, Category
        from app.orders.models import Order

        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get('q') or '').strip()
        ctx['q'] = q

        if not q:
            ctx['has_results'] = False
            return ctx

        profile = getattr(self.request.user, 'profile', None)
        es_admin = self.request.user.is_superuser or (profile and profile.es_admin)

        prod_qs = Product.objects.select_related('categoria').filter(
            Q(nombre__icontains=q) | Q(descripcion__icontains=q)
        )
        if not es_admin:
            prod_qs = prod_qs.filter(activo=True)

        ped_qs = Order.objects.select_related('vendedor').filter(
            Q(numero__icontains=q) | Q(cliente__icontains=q) | Q(notas__icontains=q)
        ).order_by('-creado')
        if not es_admin:
            ped_qs = ped_qs.filter(vendedor=self.request.user)

        cat_qs = []
        emp_qs = []
        if es_admin:
            cat_qs = Category.objects.filter(nombre__icontains=q)
            emp_qs = User.objects.select_related('profile').filter(
                Q(username__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q)
            ).exclude(profile__rol=Profile.ROL_SUPEROWNER)  # superowner no aparece en búsquedas

        ctx['productos'] = prod_qs[:15]
        ctx['productos_count'] = prod_qs.count()
        ctx['pedidos'] = ped_qs[:15]
        ctx['pedidos_count'] = ped_qs.count()
        ctx['categorias'] = cat_qs[:10] if es_admin else []
        ctx['categorias_count'] = cat_qs.count() if es_admin else 0
        ctx['empleados'] = emp_qs[:10] if es_admin else []
        ctx['empleados_count'] = emp_qs.count() if es_admin else 0
        ctx['es_admin'] = es_admin
        ctx['has_results'] = bool(
            ctx['productos_count'] or ctx['pedidos_count'] or
            ctx['categorias_count'] or ctx['empleados_count']
        )
        return ctx


# ──────────────────────────────────────────────
# Login / Logout
# ──────────────────────────────────────────────

class CustomLoginView(LoginView):
    template_name = 'users/login.html'
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Bienvenido/a {self.request.user.get_full_name() or self.request.user.username}!',
        )
        return response


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('users:login')


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

class DashboardView(LoginRequiredMixin, TemplateView):
    def get_template_names(self):
        profile = getattr(self.request.user, 'profile', None)
        if self.request.user.is_superuser or (profile and profile.es_admin):
            return ['users/dashboard_admin.html']
        return ['users/dashboard_empleado.html']

    def get_context_data(self, **kwargs):
        import json
        from decimal import Decimal
        from app.products.models import Product
        from app.orders.models import Order, OrderItem

        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        inicio_mes = hoy.replace(day=1)

        pedidos_hoy = Order.objects.filter(creado__date=hoy)
        ventas_hoy = pedidos_hoy.filter(estado=Order.ESTADO_COMPLETADO).aggregate(
            total=Sum('total'), cantidad=Count('id'),
        )
        ventas_semana = Order.objects.filter(
            creado__date__gte=inicio_semana,
            estado=Order.ESTADO_COMPLETADO,
        ).aggregate(total=Sum('total'), cantidad=Count('id'))
        ventas_mes = Order.objects.filter(
            creado__date__gte=inicio_mes,
            estado=Order.ESTADO_COMPLETADO,
        ).aggregate(total=Sum('total'), cantidad=Count('id'))

        top_productos = (
            OrderItem.objects.filter(
                pedido__creado__date__gte=inicio_mes,
                pedido__estado=Order.ESTADO_COMPLETADO,
            )
            .values('producto__nombre')
            .annotate(cantidad=Sum('cantidad'), ingresos=Sum('subtotal'))
            .order_by('-cantidad')[:5]
        )

        dias_labels = []
        dias_data = []
        for i in range(6, -1, -1):
            dia = hoy - timedelta(days=i)
            total = Order.objects.filter(
                creado__date=dia, estado=Order.ESTADO_COMPLETADO,
            ).aggregate(t=Sum('total'))['t'] or Decimal('0')
            dias_labels.append(dia.strftime('%a %d/%m'))
            dias_data.append(float(total))

        cat_qs = (
            OrderItem.objects.filter(
                pedido__creado__date__gte=inicio_mes,
                pedido__estado=Order.ESTADO_COMPLETADO,
            )
            .values('producto__categoria__nombre', 'producto__categoria__color')
            .annotate(total=Sum('subtotal'))
            .order_by('-total')
        )
        cat_labels, cat_data, cat_colors = [], [], []
        for c in cat_qs:
            cat_labels.append(c['producto__categoria__nombre'] or 'Sin categoría')
            cat_data.append(float(c['total'] or 0))
            cat_colors.append(c['producto__categoria__color'] or '#858796')

        chart_data = {
            'dias': {'labels': dias_labels, 'data': dias_data},
            'categorias': {'labels': cat_labels, 'data': cat_data, 'colors': cat_colors},
        }

        ctx.update({
            'ventas_hoy_total': ventas_hoy.get('total') or 0,
            'ventas_hoy_cantidad': ventas_hoy.get('cantidad') or 0,
            'ventas_semana_total': ventas_semana.get('total') or 0,
            'ventas_semana_cantidad': ventas_semana.get('cantidad') or 0,
            'ventas_mes_total': ventas_mes.get('total') or 0,
            'ventas_mes_cantidad': ventas_mes.get('cantidad') or 0,
            'pedidos_pendientes': Order.objects.filter(estado=Order.ESTADO_PENDIENTE).count(),
            'productos_activos': Product.objects.filter(activo=True).count(),
            'empleados_activos': User.objects.filter(
                is_active=True, profile__rol=Profile.ROL_EMPLEADO,
            ).count(),
            'mis_pedidos_hoy': pedidos_hoy.filter(vendedor=self.request.user).count(),
            'ultimos_pedidos': Order.objects.select_related('vendedor').order_by('-creado')[:8],
            'mis_ultimos_pedidos': Order.objects.filter(
                vendedor=self.request.user
            ).order_by('-creado')[:8],
            'top_productos': list(top_productos),
            'chart_data': chart_data,
        })
        return ctx


# ──────────────────────────────────────────────
# Gestión de empleados (solo admin)
# ──────────────────────────────────────────────

def _usuario_es_protegido(usuario):
    """True si el usuario es superowner y no debe ser tocado por nadie."""
    profile = getattr(usuario, 'profile', None)
    return profile and profile.es_superowner


class EmpleadoListView(AdminRequiredMixin, ListView):
    model = User
    template_name = 'users/empleado_list.html'
    context_object_name = 'empleados'
    paginate_by = 8

    def get_queryset(self):
        # Superowners nunca aparecen en la lista de empleados
        qs = User.objects.select_related('profile').exclude(
            profile__rol=Profile.ROL_SUPEROWNER
        ).order_by('-date_joined')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)
            )
        rol = self.request.GET.get('rol', '').strip()
        if rol:
            qs = qs.filter(profile__rol=rol)
        estado = self.request.GET.get('estado', '').strip()
        if estado == 'activos':
            qs = qs.filter(is_active=True)
        elif estado == 'inactivos':
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['rol'] = self.request.GET.get('rol', '')
        ctx['estado'] = self.request.GET.get('estado', '')
        # Solo mostrar admin y empleado en el filtro (nunca superowner)
        ctx['roles'] = [
            (Profile.ROL_EMPLEADO, 'Empleado'),
            (Profile.ROL_ADMIN, 'Administrador'),
        ]
        return ctx


class EmpleadoCreateView(AdminRequiredMixin, FormView):
    form_class = EmpleadoCreateForm
    template_name = 'users/empleado_form.html'
    success_url = reverse_lazy('users:empleado_list')

    def form_valid(self, form):
        user = form.save()
        messages.success(self.request, f'Usuario "{user.username}" creado correctamente.')
        return super().form_valid(form)


class EmpleadoUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = EmpleadoEditForm
    template_name = 'users/empleado_form.html'
    success_url = reverse_lazy('users:empleado_list')

    def dispatch(self, request, *args, **kwargs):
        usuario = self.get_object()
        # Protección: nadie puede editar a un superowner
        if _usuario_es_protegido(usuario):
            messages.error(request, 'Este usuario no puede ser modificado.')
            return redirect('users:empleado_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Usuario actualizado correctamente.')
        return response


class EmpleadoDeleteView(AdminRequiredMixin, DetailView):
    """Baja lógica del usuario."""
    model = User
    template_name = 'users/empleado_confirm_delete.html'
    context_object_name = 'object'

    def post(self, request, *args, **kwargs):
        usuario = self.get_object()

        # Protección 1: nadie puede desactivarse a sí mismo
        if usuario.pk == request.user.pk:
            messages.error(request, 'No podés desactivarte a vos mismo.')
            return redirect('users:empleado_list')

        # Protección 2: superowner es intocable
        if _usuario_es_protegido(usuario):
            messages.error(request, 'Este usuario del sistema no puede ser desactivado.')
            return redirect('users:empleado_list')

        usuario.is_active = False
        usuario.save(update_fields=['is_active'])
        if hasattr(usuario, 'profile'):
            usuario.profile.activo = False
            usuario.profile.save(update_fields=['activo'])

        messages.success(
            request,
            f'Usuario "{usuario.username}" desactivado. Su historial se conserva.',
        )
        return redirect('users:empleado_list')


class EmpleadoActivateView(AdminRequiredMixin, DetailView):
    """Reactiva un usuario previamente desactivado."""
    model = User

    def post(self, request, *args, **kwargs):
        usuario = self.get_object()
        if _usuario_es_protegido(usuario):
            messages.error(request, 'Este usuario no puede ser modificado.')
            return redirect('users:empleado_list')
        usuario.is_active = True
        usuario.save(update_fields=['is_active'])
        if hasattr(usuario, 'profile'):
            usuario.profile.activo = True
            usuario.profile.save(update_fields=['activo'])
        messages.success(request, f'Usuario "{usuario.username}" reactivado.')
        return redirect('users:empleado_list')

    def get(self, request, *args, **kwargs):
        return redirect('users:empleado_list')


@login_required
def perfil_view(request):
    """Vista del perfil del usuario actual."""
    profile = request.user.profile
    if request.method == 'POST':
        form = EmpleadoEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil actualizado.')
            return redirect('users:perfil')
    else:
        form = EmpleadoEditForm(instance=request.user)
    return render(request, 'users/perfil.html', {'form': form, 'profile': profile})
