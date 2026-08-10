from django.contrib import admin, messages

from app.facturacion.models import Comprobante, EmisorConfig, LogSri, SecuenciaFactura
from app.facturacion.sri import emision as sri_emision


@admin.register(EmisorConfig)
class EmisorConfigAdmin(admin.ModelAdmin):
    list_display = ('ruc', 'razon_social', 'ambiente', 'tiene_firma', 'actualizado')
    fieldsets = (
        ('Datos del emisor', {
            'fields': ('ruc', 'razon_social', 'nombre_comercial', 'direccion', 'telefono', 'email'),
        }),
        ('SRI', {
            'fields': (
                'ambiente', 'establecimiento', 'punto_emision',
                'obligado_contabilidad', 'agente_retencion', 'contribuyente_especial',
            ),
            'description': 'Ambiente 1 = pruebas (celcer.sri.gob.ec), ambiente 2 = producción (cel.sri.gob.ec). '
                           'El RUC 9999999999999 es un placeholder de prueba. Los campos de contabilidad '
                           'deben coincidir con el registro del RUC.',
        }),
        ('Firma electrónica (.p12)', {
            'fields': ('firma', 'clave_firma'),
            'description': 'Subí el archivo .p12 emitido por el SRI. Para probar sin firma real, '
                           'ejecutá `python manage.py crear_firma_prueba`.',
        }),
    )

    @admin.display(boolean=True, description='¿Firma cargada?')
    def tiene_firma(self, obj):
        return obj.tiene_firma()

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return not EmisorConfig.objects.exists()


@admin.register(SecuenciaFactura)
class SecuenciaFacturaAdmin(admin.ModelAdmin):
    list_display = ('anio', 'ultimo')
    readonly_fields = ('anio', 'ultimo')


@admin.register(Comprobante)
class ComprobanteAdmin(admin.ModelAdmin):
    list_display = (
        'numero', 'pedido_numero', 'cliente', 'total', 'estado',
        'secuencial', 'creado',
    )
    list_filter = ('estado', 'creado')
    search_fields = ('clave_acceso', 'numero_completo', 'numero_autorizacion', 'pedido__numero')
    readonly_fields = (
        'pedido', 'clave_acceso', 'numero_completo', 'secuencial', 'estado',
        'xml_firmado', 'xml_autorizado', 'numero_autorizacion', 'mensajes',
        'intentos', 'creado', 'actualizado',
    )
    actions = ('reenviar_seleccionados', 'consultar_seleccionados')

    @admin.display(description='Pedido')
    def pedido_numero(self, obj):
        return obj.pedido.numero

    @admin.display(description='Cliente')
    def cliente(self, obj):
        return obj.pedido.cliente or 'Consumidor final'

    @admin.display(description='Total')
    def total(self, obj):
        return f'${obj.pedido.total}'

    @admin.action(description='Reenviar al SRI')
    def reenviar_seleccionados(self, request, queryset):
        ok, fallo = 0, 0
        for comp in queryset.filter(estado=Comprobante.ESTADO_PENDIENTE):
            try:
                sri_emision._enviar_y_autorizar(comp)
                ok += 1
            except Exception:  # noqa: BLE001
                fallo += 1
        self.message_user(
            request, f'Reintentados: {ok} · fallidos: {fallo}',
            level=messages.SUCCESS if fallo == 0 else messages.WARNING,
        )

    @admin.action(description='Consultar autorización')
    def consultar_seleccionados(self, request, queryset):
        emisor = EmisorConfig.obtener()
        ok, fallo = 0, 0
        for comp in queryset.filter(estado=Comprobante.ESTADO_ENVIADA):
            try:
                sri_emision._consultar_autorizacion(comp, emisor)
                ok += 1
            except Exception:  # noqa: BLE001
                fallo += 1
        self.message_user(
            request, f'Consultadas: {ok} · con error: {fallo}',
            level=messages.SUCCESS if fallo == 0 else messages.WARNING,
        )


@admin.register(LogSri)
class LogSriAdmin(admin.ModelAdmin):
    list_display = ('creado', 'nivel', 'comprobante', 'mensaje')
    list_filter = ('nivel', 'creado')
    search_fields = ('mensaje', 'comprobante__clave_acceso')
    readonly_fields = ('creado',)
