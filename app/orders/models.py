"""Modelos de pedidos."""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.urls import reverse

from app.products.models import Product


class Order(models.Model):
    """Pedido o venta del puesto."""

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_COMPLETADO = 'completado'
    ESTADO_CANCELADO = 'cancelado'
    ESTADO_CHOICES = (
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_COMPLETADO, 'Completado'),
        (ESTADO_CANCELADO, 'Cancelado'),
    )

    METODO_EFECTIVO = 'efectivo'
    METODO_TARJETA = 'tarjeta'
    METODO_TRANSFER = 'transferencia'
    METODO_QR = 'qr'
    METODO_CHOICES = (
        (METODO_EFECTIVO, 'Efectivo'),
        (METODO_TARJETA, 'Tarjeta'),
        (METODO_TRANSFER, 'Transferencia'),
        (METODO_QR, 'QR'),
    )

    TIPO_IDENTIFICACION_CHOICES = (
        ('04', 'RUC'),
        ('05', 'Cédula'),
        ('06', 'Pasaporte'),
        ('07', 'Consumidor Final'),
    )

    numero = models.CharField('Número', max_length=20, unique=True, blank=True)
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='ventas', verbose_name='Vendedor',
    )
    cliente = models.CharField('Cliente', max_length=120, blank=True)
    nombres = models.CharField('Nombres', max_length=60, blank=True, default='')
    apellidos = models.CharField('Apellidos', max_length=60, blank=True, default='')
    tipo_identificacion = models.CharField(
        'Tipo de identificación', max_length=2, choices=TIPO_IDENTIFICACION_CHOICES,
        blank=True, null=True
    )
    identificacion = models.CharField('Identificación', max_length=20, blank=True, null=True)
    direccion = models.CharField('Dirección', max_length=300, blank=True, null=True)
    telefono = models.CharField('Teléfono', max_length=30, blank=True, null=True)
    email = models.EmailField('Email', blank=True, null=True)
    estado = models.CharField(
        'Estado', max_length=15, choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE, db_index=True,
    )
    metodo_pago = models.CharField(
        'Método de pago', max_length=20, choices=METODO_CHOICES,
        default=METODO_EFECTIVO,
    )
    subtotal = models.DecimalField(
        'Subtotal', max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    descuento = models.DecimalField(
        'Descuento', max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    total = models.DecimalField(
        'Total', max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    
    # Campos para facturación electrónica (SRI)
    secuencial_factura = models.CharField('Secuencial de factura', max_length=17, blank=True, null=True)
    clave_acceso = models.CharField('Clave de acceso', max_length=49, blank=True, null=True)
    subtotal_iva = models.DecimalField('Subtotal IVA', max_digits=12, decimal_places=2, blank=True, null=True)
    subtotal_cero = models.DecimalField('Subtotal Cero', max_digits=12, decimal_places=2, blank=True, null=True)
    valor_iva = models.DecimalField('Valor IVA', max_digits=12, decimal_places=2, blank=True, null=True)

    notas = models.TextField('Notas especiales', blank=True)
    creado = models.DateTimeField('Creado', auto_now_add=True, db_index=True)
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    class Meta:
        verbose_name = 'Pedido'
        verbose_name_plural = 'Pedidos'
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['estado', '-creado']),
            models.Index(fields=['vendedor', '-creado']),
        ]

    def __str__(self):
        return f'Pedido {self.numero or self.pk} (${self.total})'

    def get_absolute_url(self):
        return reverse('orders:order_detail', args=[self.pk])

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.numero:
            self.numero = f'P-{self.creado:%Y%m%d}-{self.pk:05d}'
            super().save(update_fields=['numero'])

    @transaction.atomic
    def recalcular_totales(self):
        agg = self.items.aggregate(total=models.Sum('subtotal'))
        self.subtotal = agg['total'] or Decimal('0.00')
        self.total = max(self.subtotal - self.descuento, Decimal('0.00'))
        # Desglose SRI: todos los ítems pagan IVA por ahora
        self.subtotal_iva = self.subtotal
        self.subtotal_cero = Decimal('0.00')
        self.valor_iva = self.iva_subtotal
        self.save(update_fields=[
            'subtotal', 'total', 'subtotal_iva', 'subtotal_cero',
            'valor_iva', 'actualizado',
        ])

    @transaction.atomic
    def completar(self, usuario=None):
        """Marca el pedido como completado."""
        if self.estado == self.ESTADO_COMPLETADO:
            return
        self.estado = self.ESTADO_COMPLETADO
        self.save(update_fields=['estado', 'actualizado'])

    def cancelar(self):
        self.estado = self.ESTADO_CANCELADO
        self.save(update_fields=['estado', 'actualizado'])

    # ---------- Desglose de IVA ----------
    # La alícuota sale de settings (IVA_RATE), default 15% (Ecuador SRI).
    @property
    def iva_alicuota(self):
        return getattr(settings, 'IVA_RATE', Decimal('0.15'))

    @property
    def subtotal_sin_iva(self):
        """Subtotal sin IVA (subtotal - IVA)."""
        return (self.subtotal - self.iva_subtotal).quantize(Decimal('0.01'))

    @property
    def iva_subtotal(self):
        """IVA sobre el subtotal: subtotal × alícuota."""
        return (self.subtotal * self.iva_alicuota).quantize(Decimal('0.01'))


class Cliente(models.Model):
    """Cliente habitual: datos del receptor acumulados entre ventas.

    Se guarda automáticamente al cobrar (nunca para Consumidor Final) y
    se identifica por (tipo_identificacion, identificacion), que es único:
    la cédula/RUC/pasaporte no se repite entre personas.
    """

    TIPO_CONSUMIDOR = '07'

    tipo_identificacion = models.CharField(
        'Tipo de identificación', max_length=2, choices=Order.TIPO_IDENTIFICACION_CHOICES,
    )
    identificacion = models.CharField('Identificación', max_length=20)
    nombre = models.CharField('Nombre / Razón social', max_length=120)
    nombres = models.CharField('Nombres', max_length=60, blank=True, default='')
    apellidos = models.CharField('Apellidos', max_length=60, blank=True, default='')
    direccion = models.CharField('Dirección', max_length=300, blank=True, default='')
    email = models.EmailField('Email', blank=True, null=True)
    telefono = models.CharField('Teléfono', max_length=30, blank=True, default='')
    creado = models.DateTimeField('Creado', auto_now_add=True)
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(
                fields=['tipo_identificacion', 'identificacion'],
                name='uniq_cliente_tipo_identificacion',
            ),
        ]

    def __str__(self):
        return f'{self.nombre} ({self.identificacion})'


class OrderItem(models.Model):
    """Línea de detalle de un pedido."""

    pedido = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='items'
    )
    producto = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='ventas_items'
    )
    cantidad = models.PositiveIntegerField(
        'Cantidad',
        default=1,
        validators=[MinValueValidator(1)],
    )
    precio_unitario = models.DecimalField(
        'Precio unitario', max_digits=10, decimal_places=2,
    )
    subtotal = models.DecimalField(
        'Subtotal', max_digits=12, decimal_places=2, default=Decimal('0.00')
    )
    nota = models.CharField('Nota', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Detalle de pedido'
        verbose_name_plural = 'Detalles de pedido'

    def __str__(self):
        return f'{self.cantidad} x {self.producto.nombre}'

    def save(self, *args, **kwargs):
        self.subtotal = (self.precio_unitario or Decimal('0')) * (self.cantidad or Decimal('0'))
        super().save(*args, **kwargs)
