"""Context processors globales."""
from django.conf import settings


def business_info(request):
    return {
        'NEGOCIO_NOMBRE': getattr(settings, 'NEGOCIO_NOMBRE', 'Doña Sara'),
    }


def topbar_notifs(request):
    """Notificaciones y mensajes que se muestran en la topbar.

    Se ejecuta en cada request autenticado. Para usuarios anónimos
    devuelve ceros para no hacer queries innecesarias.
    """
    if not request.user.is_authenticated:
        return {
            'topbar_alertas_count': 0,
            'topbar_alertas': [],
            'topbar_mensajes_count': 0,
            'topbar_mensajes': [],
        }

    from app.orders.models import Order

    profile = getattr(request.user, 'profile', None)
    es_admin = request.user.is_superuser or (profile and profile.es_admin)

    # Alertas: pedidos pendientes (admin ve todos, empleado solo los suyos)
    pendientes_qs = Order.objects.filter(estado=Order.ESTADO_PENDIENTE)
    if not es_admin:
        pendientes_qs = pendientes_qs.filter(vendedor=request.user)

    # Una sola query salvo que haya más de 5 pendientes (entonces sí contamos)
    alertas = list(pendientes_qs.select_related('vendedor').order_by('-creado')[:5])
    if len(alertas) == 5:
        alertas_count = pendientes_qs.count()
    else:
        alertas_count = len(alertas)

    # Mensajes: por ahora vacío (lista lista para extender)
    return {
        'topbar_alertas_count': alertas_count,
        'topbar_alertas': alertas,
        'topbar_mensajes_count': 0,
        'topbar_mensajes': [],
    }
