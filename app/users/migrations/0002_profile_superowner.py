"""Migración: agrega el rol superowner al campo Profile.rol."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='profile',
            name='rol',
            field=models.CharField(
                choices=[
                    ('superowner', 'Propietario del sistema'),
                    ('admin', 'Administrador'),
                    ('empleado', 'Empleado'),
                ],
                db_index=True,
                default='empleado',
                max_length=20,
                verbose_name='Rol',
            ),
        ),
    ]
