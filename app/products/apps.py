from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.products'
    label = 'products'
    verbose_name = 'Productos e Ingredientes'
