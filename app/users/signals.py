"""Señales para crear el perfil automaticamente al crear un usuario."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Profile


@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance, created, **kwargs):
    if created:
        rol = Profile.ROL_ADMIN if instance.is_superuser else Profile.ROL_EMPLEADO
        Profile.objects.create(user=instance, rol=rol)
    else:
        Profile.objects.get_or_create(user=instance)
