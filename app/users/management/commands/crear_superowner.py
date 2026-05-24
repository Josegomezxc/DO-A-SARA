"""
Comando para crear el usuario superowner del sistema.

Uso:
    python manage.py crear_superowner
    python manage.py crear_superowner --username miusuario --password mipass

El superowner es el dueño del SaaS. Tiene acceso completo a todo,
nadie puede editarlo ni eliminarlo desde el panel.
"""
import getpass
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from app.users.models import Profile


class Command(BaseCommand):
    help = 'Crea el usuario propietario del sistema (superowner). Solo debe ejecutarse una vez.'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Nombre de usuario')
        parser.add_argument('--password', type=str, help='Contraseña (mejor ingresarla interactivamente)')

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n=== Creación del Propietario del Sistema ===\n'))

        # Verificar si ya existe un superowner
        existing = Profile.objects.filter(rol=Profile.ROL_SUPEROWNER).first()
        if existing:
            self.stdout.write(self.style.ERROR(
                f'Ya existe un superowner: "{existing.user.username}". '
                'Solo puede haber uno. Si necesitás cambiar la contraseña, usá:\n'
                '  python manage.py cambiar_password_superowner'
            ))
            sys.exit(1)

        username = options.get('username') or input('Nombre de usuario: ').strip()
        if not username:
            raise CommandError('El nombre de usuario no puede estar vacío.')

        if User.objects.filter(username=username).exists():
            raise CommandError(f'Ya existe un usuario con el nombre "{username}".')

        if options.get('password'):
            password = options['password']
        else:
            password = getpass.getpass('Contraseña: ')
            confirm = getpass.getpass('Confirmar contraseña: ')
            if password != confirm:
                raise CommandError('Las contraseñas no coinciden.')

        if len(password) < 10:
            raise CommandError('La contraseña del superowner debe tener al menos 10 caracteres.')

        user = User.objects.create_user(
            username=username,
            password=password,
            is_staff=True,
            is_superuser=True,
        )
        profile = user.profile
        profile.rol = Profile.ROL_SUPEROWNER
        profile.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Superowner "{username}" creado exitosamente.\n'
            '  - Tiene acceso completo al sistema\n'
            '  - No puede ser editado ni eliminado desde el panel\n'
            '  - Guardá estas credenciales en un lugar seguro\n'
        ))
