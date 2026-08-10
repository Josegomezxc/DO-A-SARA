"""Modelos de facturación electrónica (SRI Ecuador).

Flujo:
  - `EmisorConfig`: datos fiscales del negocio (singleton).
  - `SecuenciaFactura`: secuencial por año (evita duplicados con
    select_for_update).
  - `Comprobante`: la factura XML firmada de un pedido y su estado
    frente al SRI.
  - `LogSri`: bitácora de intentos, envíos y errores.
"""
from django.core.validators import MinLengthValidator
from django.db import models
from django.utils import timezone


class EmisorConfig(models.Model):
    """Datos del emisor (una sola fila)."""

    AMBIENTE_PRUEBAS = '1'
    AMBIENTE_PRODUCCION = '2'
    AMBIENTE_CHOICES = (
        (AMBIENTE_PRUEBAS, 'Pruebas (ambiente 1)'),
        (AMBIENTE_PRODUCCION, 'Producción (ambiente 2)'),
    )

    ruc = models.CharField(
        'RUC', max_length=13, default='9999999999999',
        validators=[MinLengthValidator(13)],
        help_text='RUC del negocio (placeholder 9999999999999 mientras no haya RUC real).',
    )
    razon_social = models.CharField('Razón social', max_length=300, default='EMPRESA DE PRUEBA SRI')
    nombre_comercial = models.CharField('Nombre comercial', max_length=300, blank=True)
    direccion = models.CharField('Dirección (matriz)', max_length=300, default='Quito, Ecuador')
    telefono = models.CharField('Teléfono', max_length=30, blank=True)
    email = models.EmailField('Email', blank=True)
    obligado_contabilidad = models.BooleanField(
        'Obligado a llevar contabilidad', default=False,
        help_text='Marcar solo si el RUC está registrado como obligado a llevar '
                  'contabilidad (personas naturales: NO).',
    )
    agente_retencion = models.BooleanField(
        'Agente de retención', default=False,
        help_text='Marcar solo si el RUC está registrado como agente de retención.',
    )
    contribuyente_especial = models.CharField(
        'N.º resolución de contribuyente especial', max_length=13, blank=True,
        help_text='Dejar vacío si no es contribuyente especial (máx. 13 caracteres).',
    )
    ambiente = models.CharField(
        'Ambiente', max_length=1, choices=AMBIENTE_CHOICES, default=AMBIENTE_PRUEBAS,
        help_text='1 = pruebas (celcer), 2 = producción (cel).',
    )
    establecimiento = models.CharField('Establecimiento', max_length=3, default='001')
    punto_emision = models.CharField('Punto de emisión', max_length=3, default='001')
    firma = models.FileField(
        'Firma electrónica (.p12)', upload_to='firmas/', blank=True, null=True,
        help_text='Archivo .p12 emitido por el SRI (o el generado por '
                  '`crear_firma_prueba`).',
    )
    clave_firma = models.CharField(
        'Clave de la firma', max_length=100, blank=True,
        help_text='Contraseña del archivo .p12.',
    )
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    class Meta:
        verbose_name = 'Configuración de facturación'
        verbose_name_plural = 'Configuración de facturación'

    def __str__(self):
        return f'Emisor {self.ruc} (ambiente {self.ambiente})'

    @classmethod
    def obtener(cls):
        """Devuelve la única fila de configuración (la crea si no existe)."""
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            'ruc': '9999999999999',
            'razon_social': 'EMPRESA DE PRUEBA SRI',
            'direccion': 'Quito, Ecuador',
        })
        return obj

    def tiene_firma(self):
        return bool(self.firma and self.clave_firma)


class SecuenciaFactura(models.Model):
    """Secuencial de facturación por año (001-001-000000001...)."""

    anio = models.PositiveIntegerField('Año', unique=True)
    ultimo = models.PositiveIntegerField('Último secuencial usado', default=0)

    class Meta:
        verbose_name = 'Secuencia de factura'
        verbose_name_plural = 'Secuencias de factura'

    def __str__(self):
        return f'{self.anio}: {self.ultimo}'

    def siguiente(self):
        """Avanza y devuelve el próximo secuencial.

        Debe llamarse dentro de una transacción con `select_for_update`
        para que dos pedidos simultáneos no repitan número.
        """
        self.ultimo += 1
        self.save(update_fields=['ultimo'])
        return self.ultimo


class Comprobante(models.Model):
    """Factura electrónica de un pedido (uno por pedido)."""

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ENVIADA = 'enviada'
    ESTADO_AUTORIZADA = 'autorizada'
    ESTADO_RECHAZADA = 'rechazada'
    ESTADO_CHOICES = (
        (ESTADO_PENDIENTE, 'Pendiente de envío'),
        (ESTADO_ENVIADA, 'Enviada (esperando autorización)'),
        (ESTADO_AUTORIZADA, 'Autorizada'),
        (ESTADO_RECHAZADA, 'Rechazada'),
    )

    pedido = models.OneToOneField(
        'orders.Order', on_delete=models.PROTECT, related_name='comprobante',
        verbose_name='Pedido',
    )
    clave_acceso = models.CharField('Clave de acceso', max_length=49, unique=True)
    numero_completo = models.CharField('Número (estab-pto-sec)', max_length=17, unique=True)
    secuencial = models.PositiveIntegerField('Secuencial', db_index=True)
    estado = models.CharField(
        'Estado', max_length=15, choices=ESTADO_CHOICES,
        default=ESTADO_PENDIENTE, db_index=True,
    )
    xml_firmado = models.TextField('XML firmado')
    xml_autorizado = models.TextField('XML autorizado (SRI)', blank=True)
    numero_autorizacion = models.CharField('Número de autorización', max_length=49, blank=True)
    mensajes = models.TextField('Mensajes del SRI', blank=True)
    intentos = models.PositiveIntegerField('Intentos de envío', default=0)
    creado = models.DateTimeField('Creado', auto_now_add=True)
    actualizado = models.DateTimeField('Actualizado', auto_now=True)

    class Meta:
        verbose_name = 'Comprobante'
        verbose_name_plural = 'Comprobantes'
        ordering = ['-creado']
        indexes = [
            models.Index(fields=['estado', 'creado']),
        ]

    def __str__(self):
        return f'{self.numero_completo} ({self.get_estado_display()})'

    @property
    def numero(self):
        """Formato 001-001-000000001 para mostrar."""
        n = self.numero_completo
        return f'{n[:3]}-{n[3:6]}-{n[6:]}' if len(n) == 15 else n


class LogSri(models.Model):
    """Bitácora de eventos de facturación."""

    NIVEL_INFO = 'info'
    NIVEL_WARNING = 'warning'
    NIVEL_ERROR = 'error'
    NIVEL_CHOICES = (
        (NIVEL_INFO, 'Info'),
        (NIVEL_WARNING, 'Advertencia'),
        (NIVEL_ERROR, 'Error'),
    )

    comprobante = models.ForeignKey(
        Comprobante, on_delete=models.CASCADE, related_name='logs',
        verbose_name='Comprobante', blank=True, null=True,
    )
    nivel = models.CharField('Nivel', max_length=10, choices=NIVEL_CHOICES, default=NIVEL_INFO)
    mensaje = models.TextField('Mensaje')
    creado = models.DateTimeField('Creado', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Log SRI'
        verbose_name_plural = 'Logs SRI'
        ordering = ['-creado']

    def __str__(self):
        return f'[{self.get_nivel_display()}] {self.mensaje[:80]}'
