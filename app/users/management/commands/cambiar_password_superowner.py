"""
Comando para cambiar la contraseña del superowner.

Uso:
    python manage.py cambiar_password_superowner
"""
import getpass
import sys

from django.core.management.base import BaseCommand, CommandError

from app.users.models import Profile


class Command(BaseCommand):
    help = 'Cambia la contraseña del superowner.'

    def handle(self, *args, **options):
        profile = Profile.objects.filter(rol=Profile.ROL_SUPEROWNER).select_related('user').first()
        if not profile:
            raise CommandError('No existe ningún superowner. Ejecutá primero: python manage.py crear_superowner')

        self.stdout.write(f'Cambiando contraseña del superowner: "{profile.user.username}"')

        password = getpass.getpass('Nueva contraseña: ')
        confirm = getpass.getpass('Confirmar contraseña: ')

        if password != confirm:
            raise CommandError('Las contraseñas no coinciden.')
        if len(password) < 10:
            raise CommandError('La contraseña debe tener al menos 10 caracteres.')

        profile.user.set_password(password)
        profile.user.save()

        self.stdout.write(self.style.SUCCESS('✓ Contraseña actualizada correctamente.'))
