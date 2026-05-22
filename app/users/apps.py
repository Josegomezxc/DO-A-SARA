from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.users'
    label = 'users'
    verbose_name = 'Usuarios y Autenticación'

    def ready(self):
        from . import signals  # noqa: F401
