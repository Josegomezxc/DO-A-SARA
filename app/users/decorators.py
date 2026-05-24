"""Decoradores y mixins para control de acceso por rol."""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect


def _es_admin_o_superior(user):
    """True si el usuario es admin, superowner o superuser de Django."""
    profile = getattr(user, 'profile', None)
    return user.is_superuser or (profile and profile.es_admin)


def _es_superowner(user):
    profile = getattr(user, 'profile', None)
    return profile and profile.es_superowner


def admin_required(view_func):
    """Permite solo a usuarios con rol administrador, superowner o superuser."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if _es_admin_o_superior(request.user):
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tenés permisos para acceder a esta sección.')
        return redirect('users:dashboard')

    return _wrapped


def empleado_required(view_func):
    """Permite a empleados y admins."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if request.user.is_active:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Tu cuenta está inactiva.')
        return redirect('users:login')

    return _wrapped


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin de CBV: requiere rol administrador o superior."""

    raise_exception = False
    permission_denied_message = 'Sólo administradores pueden acceder a esta sección.'

    def test_func(self):
        return _es_admin_o_superior(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, self.permission_denied_message)
            return redirect('users:dashboard')
        return super().handle_no_permission()


class EmpleadoRequiredMixin(LoginRequiredMixin):
    """Mixin de CBV: requiere usuario autenticado y activo."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_active:
            messages.error(request, 'Tu cuenta está inactiva.')
            return redirect('users:login')
        return super().dispatch(request, *args, **kwargs)
