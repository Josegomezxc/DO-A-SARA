"""Modelos para el catálogo del local (categorías y productos)."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Category(models.Model):
    """Categoría del menú (Salchipapas, Hamburguesas, Extras, ...)."""

    nombre = models.CharField('Nombre', max_length=80, unique=True)
    slug = models.SlugField('Slug', max_length=90, unique=True, blank=True)
    descripcion = models.TextField('Descripción', blank=True)
    icono = models.CharField(
        'Ícono', max_length=60, blank=True,
        help_text='Ej: fas fa-hamburger, fas fa-fire'
    )
    color = models.CharField(
        'Color', max_length=20, default='#fb8500',
        help_text='Color hexadecimal para distinguir la categoría'
    )
    orden = models.PositiveIntegerField('Orden', default=0)
    activa = models.BooleanField('Activa', default=True)

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('products:category_list')


class Product(models.Model):
    """Producto vendible del menú (hamburguesa, salchipapa, bebida, etc.)."""

    nombre = models.CharField('Nombre', max_length=140, db_index=True)
    descripcion = models.TextField('Descripción', blank=True)
    categoria = models.ForeignKey(
        Category, on_delete=models.PROTECT,
        related_name='productos', verbose_name='Categoría',
    )
    precio = models.DecimalField(
        'Precio de venta', max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    imagen = models.FileField(
        'Imagen', upload_to='productos/', blank=True, null=True,
        help_text='Imagen del producto (JPG/PNG).'
    )
    activo = models.BooleanField('Activo', default=True, db_index=True)
    creado = models.DateTimeField('Creado', auto_now_add=True)
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        ordering = ['categoria__orden', 'nombre']
        indexes = [
            models.Index(fields=['activo', 'categoria']),
        ]

    def __str__(self):
        return f'{self.nombre} (${self.precio})'

    def get_absolute_url(self):
        return reverse('products:product_list')
