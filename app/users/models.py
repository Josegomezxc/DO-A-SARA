"""Modelos de usuarios y perfiles del sistema."""
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse


class Profile(models.Model):
    """Perfil extendido del usuario con rol y datos adicionales."""

    ROL_SUPEROWNER = 'superowner'   # Dueño del SaaS — protegido, no editable por nadie
    ROL_ADMIN = 'admin'             # Admin del negocio cliente
    ROL_EMPLEADO = 'empleado'       # Empleado del negocio cliente

    ROL_CHOICES = (
        (ROL_SUPEROWNER, 'Propietario del sistema'),
        (ROL_ADMIN, 'Administrador'),
        (ROL_EMPLEADO, 'Empleado'),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Usuario',
    )
    rol = models.CharField(
        'Rol',
        max_length=20,
        choices=ROL_CHOICES,
        default=ROL_EMPLEADO,
        db_index=True,
    )
    telefono = models.CharField('Teléfono', max_length=30, blank=True)
    documento = models.CharField('Documento', max_length=30, blank=True)
    activo = models.BooleanField('Activo', default=True)
    creado = models.DateTimeField('Creado', auto_now_add=True)
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'
        ordering = ['user__username']

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.get_rol_display()})'

    @property
    def es_superowner(self):
        return self.rol == self.ROL_SUPEROWNER

    @property
    def es_admin(self):
        return self.rol in (self.ROL_ADMIN, self.ROL_SUPEROWNER) or self.user.is_superuser

    @property
    def es_empleado(self):
        return self.rol == self.ROL_EMPLEADO

    def get_absolute_url(self):
        return reverse('users:dashboard')
