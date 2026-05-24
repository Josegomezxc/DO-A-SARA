"""
Comando para dar acceso a un nuevo cliente del SaaS.

Uso:
    python manage.py dar_acceso_cliente
    python manage.py dar_acceso_cliente --username cliente1 --password pass123 --rol admin

El cliente recibe un usuario con rol 'admin' (por defecto) o 'empleado'.
Vos como superowner siempre mantenés el control.
"""
import getpass
import secrets
import string
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from app.users.models import Profile


def generar_password(longitud=14):
    """Genera una contraseña segura aleatoria."""
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(chars) for _ in range(longitud))


class Command(BaseCommand):
    help = 'Crea un usuario de acceso para un cliente del SaaS.'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Nombre de usuario para el cliente')
        parser.add_argument('--password', type=str, help='Contraseña (si no se pone, se genera una)')
        parser.add_argument(
            '--rol',
            type=str,
            choices=['admin', 'empleado'],
            default='admin',
            help='Rol del usuario (default: admin)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n=== Crear acceso para cliente ===\n'))

        username = options.get('username') or input('Nombre de usuario para el cliente: ').strip()
        if not username:
            raise CommandError('El nombre de usuario no puede estar vacío.')

        if User.objects.filter(username__iexact=username).exists():
            raise CommandError(f'Ya existe un usuario con el nombre "{username}".')

        reserved = ['owner', 'superowner', 'root', 'admin', 'administrator']
        if username.lower() in reserved:
            raise CommandError(f'El nombre "{username}" está reservado.')

        password = options.get('password')
        auto_generada = False
        if not password:
            resp = input('¿Generar contraseña automáticamente? [S/n]: ').strip().lower()
            if resp in ('', 's', 'si', 'yes', 'y'):
                password = generar_password()
                auto_generada = True
            else:
                password = getpass.getpass('Contraseña: ')
                confirm = getpass.getpass('Confirmar contraseña: ')
                if password != confirm:
                    raise CommandError('Las contraseñas no coinciden.')

        if len(password) < 8:
            raise CommandError('La contraseña debe tener al menos 8 caracteres.')

        rol = options.get('rol') or 'admin'

        user = User.objects.create_user(username=username, password=password)
        profile = user.profile
        profile.rol = rol
        profile.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Usuario "{username}" creado con rol "{rol}".'
        ))
        if auto_generada:
            self.stdout.write(self.style.WARNING(
                f'\n  Contraseña generada: {password}\n'
                '  ← Anotá esto y envíaselo al cliente de forma segura.\n'
            ))
        else:
            self.stdout.write('  Contraseña configurada por vos.\n')

        self.stdout.write(self.style.HTTP_INFO(
            '\n  RECORDÁ: Vos como superowner podés desactivar este usuario\n'
            '  cuando sea necesario desde el panel de administración.\n'
        ))
