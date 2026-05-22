from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.orders'
    label = 'orders'
    verbose_name = 'Pedidos y Caja'
