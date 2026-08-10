"""Orquestador de emisión de facturas electrónicas (idempotente).

Flujo por pedido:
  1. Reserva secuencial del año (select_for_update).
  2. Genera clave de acceso, construye y firma el XML.
  3. Guarda el `Comprobante` como pendiente.
  4. Envía a Recepción (con reintento inmediato) y consulta la
     autorización una vez. Si algo falla, queda pendiente y el comando
     `facturacion_pendientes` reintenta después.
"""
import logging
import secrets
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from app.facturacion.models import Comprobante, EmisorConfig, LogSri, SecuenciaFactura

from .clave_acceso import generar_clave_acceso
from .firma import firmar_xml_bytes
from . import servicio_sri
from .xml_builder import construir_xml

logger = logging.getLogger(__name__)


class FirmaNoConfigurada(Exception):
    """No hay firma electrónica (.p12) cargada en EmisorConfig."""


class EmisorInvalido(Exception):
    """La configuración del emisor no permite emitir (RUC inválido, etc.)."""


class PedidoInvalido(Exception):
    """El pedido no puede facturarse (no está completado)."""


def _log(comprobante, nivel, mensaje):
    LogSri.objects.create(comprobante=comprobante, nivel=nivel, mensaje=mensaje)


def _validar_emisor(emisor):
    """Valida la configuración del emisor antes de generar el XML.

    El objetivo es que ningún dato inválido llegue al SRI: mejor un
    error claro local que un rechazo del webservice.
    """
    from app.orders.validators import es_ruc_valido

    ruc = (emisor.ruc or '').strip()
    if not es_ruc_valido(ruc):
        raise EmisorInvalido(
            'El RUC configurado no es válido (dígito verificador incorrecto). '
            'Revise los datos en Configuración de facturación.'
        )
    if not (emisor.razon_social or '').strip():
        raise EmisorInvalido(
            'La razón social no puede estar vacía. '
            'Revise los datos en Configuración de facturación.'
        )
    if not (emisor.direccion or '').strip():
        raise EmisorInvalido(
            'La dirección de la matriz no puede estar vacía. '
            'Revise los datos en Configuración de facturación.'
        )


def _validar_firma_ruc(emisor):
    """La firma (.p12) debe pertenecer al RUC configurado.

    Evita emitir con una firma de otro RUC (rechazo 45 del SRI) o con
    una firma de prueba: mejor bloquear localmente antes de enviar.
    """
    from .firma import obtener_ruc_certificado

    try:
        ruc_firma = obtener_ruc_certificado(emisor.firma.path, emisor.clave_firma)
    except (ValueError, OSError):
        raise EmisorInvalido(
            'No se pudo leer la firma electrónica (.p12). Revise que el '
            'archivo sea válido y que la contraseña sea la correcta.'
        ) from None

    if ruc_firma is None:
        raise EmisorInvalido(
            'La firma electrónica no contiene un RUC válido. Solo sirven las '
            'firmas emitidas por el SRI (Security Data, ANF o BCE) con el RUC '
            'embebido; la firma de prueba no sirve para emitir comprobantes.'
        )
    if ruc_firma != emisor.ruc:
        raise EmisorInvalido(
            f'La firma electrónica pertenece al RUC {ruc_firma}, pero la '
            f'configuración usa {emisor.ruc}. Corrija la configuración o '
            'cargue la firma del RUC correcto.'
        )


def emitir_factura(pedido):
    """Emite la factura de un pedido completado. Devuelve el Comprobante.

    Idempotente: si el pedido ya tiene comprobante autorizado o enviado
    lo devuelve tal cual; si está pendiente reintenta el envío.
    """
    # Se consulta la BD directamente (no getattr(pedido, 'comprobante')):
    # la caché del reverse accessor puede quedar desactualizada si el
    # comprobante fue borrado.
    comp = Comprobante.objects.filter(pedido=pedido).first()
    if comp and comp.estado in (
        Comprobante.ESTADO_ENVIADA,
        Comprobante.ESTADO_AUTORIZADA,
    ):
        return comp

    if pedido.estado != pedido.ESTADO_COMPLETADO:
        raise PedidoInvalido(
            f'El pedido {pedido.numero} debe estar completado para facturarse.'
        )

    if not comp:
        emisor = EmisorConfig.obtener()
        _validar_emisor(emisor)
        if not emisor.tiene_firma():
            raise FirmaNoConfigurada(
                'No hay firma electrónica configurada. Cargá el .p12 y su clave '
                'en Configuración de facturación (o ejecutá `crear_firma_prueba`).'
            )
        _validar_firma_ruc(emisor)

        with transaction.atomic():
            secuencia, _ = SecuenciaFactura.objects.select_for_update().get_or_create(
                anio=timezone.now().year, defaults={'ultimo': 0}
            )
            secuencial = secuencia.siguiente()
            numero_completo = (
                f'{emisor.establecimiento}{emisor.punto_emision}{secuencial:09d}'
            )
            fecha_emision = timezone.localdate()
            clave = _generar_clave(emisor, secuencial, fecha_emision)
            xml = construir_xml(emisor, pedido, clave, secuencial, numero_completo,
                                fecha_emision=fecha_emision)
            xml_firmado = firmar_xml_bytes(xml, emisor.firma.path, emisor.clave_firma)
            pedido.secuencial_factura = numero_completo
            pedido.clave_acceso = clave
            pedido.save(update_fields=['secuencial_factura', 'clave_acceso', 'actualizado'])
            comp = Comprobante.objects.create(
                pedido=pedido,
                clave_acceso=clave,
                numero_completo=numero_completo,
                secuencial=secuencial,
                xml_firmado=xml_firmado.decode('utf-8'),
            )
        _log(comp, LogSri.NIVEL_INFO, f'Comprobante {comp.numero} generado y firmado.')

    if comp.estado == Comprobante.ESTADO_PENDIENTE:
        _enviar_y_autorizar(comp)
    return comp


def _generar_clave(emisor, secuencial, fecha):
    codigo = f'{secrets.randbelow(10 ** 8):08d}'
    return generar_clave_acceso(
        fecha=fecha,
        ruc=emisor.ruc,
        ambiente=emisor.ambiente,
        serie=f'{emisor.establecimiento}{emisor.punto_emision}',
        secuencial=secuencial if secuencial is not None else 0,
        codigo_numerico=codigo,
        tipo_emision='1',  # emisión normal (no contingencia)
    )


def _enviar_y_autorizar(comp):
    """Envía el comprobante y consulta la autorización una vez."""
    emisor = EmisorConfig.obtener()
    comp.intentos += 1
    comp.save(update_fields=['intentos', 'actualizado'])
    try:
        envio = servicio_sri.enviar(comp.xml_firmado, emisor.ambiente)
    except Exception as exc:  # noqa: BLE001
        _log(comp, LogSri.NIVEL_ERROR, f'Error de red al enviar: {exc}')
        logger.exception('Fallo de envío del comprobante %s', comp.numero_completo)
        return

    mensajes = '; '.join(envio['mensajes'])
    estado_sri = envio['estado']

    if estado_sri == 'DEVUELTA':
        comp.estado = Comprobante.ESTADO_RECHAZADA
        comp.mensajes = mensajes or 'Comprobante devuelto por el SRI.'
        comp.save(update_fields=['estado', 'mensajes', 'actualizado'])
        _log(comp, LogSri.NIVEL_ERROR, f'Recepción devolvió el comprobante: {mensajes}')
        return

    if estado_sri != 'RECIBIDA':
        _log(comp, LogSri.NIVEL_WARNING,
             f'Recepción respondió estado inesperado "{estado_sri}": {mensajes}')

    comp.estado = Comprobante.ESTADO_ENVIADA
    comp.save(update_fields=['estado', 'actualizado'])
    _log(comp, LogSri.NIVEL_INFO, 'Comprobante RECIBIDO por el SRI.')

    _consultar_autorizacion(comp, emisor)


def _consultar_autorizacion(comp, emisor):
    """Consulta la autorización; si está EN PROCESO queda enviada."""
    try:
        resp = servicio_sri.consultar_autorizacion(comp.clave_acceso, emisor.ambiente)
    except Exception as exc:  # noqa: BLE001
        _log(comp, LogSri.NIVEL_WARNING, f'Error al consultar autorización: {exc}')
        return

    estado = resp['estado']
    if estado == 'AUTORIZADO':
        comp.estado = Comprobante.ESTADO_AUTORIZADA
        comp.numero_autorizacion = resp['numero_autorizacion']
        comp.xml_autorizado = resp['xml_autorizado']
        comp.save(update_fields=[
            'estado', 'numero_autorizacion', 'xml_autorizado', 'actualizado',
        ])
        _log(comp, LogSri.NIVEL_INFO,
             f'AUTORIZADO ({resp["numero_autorizacion"]}).')
    elif estado == 'NO AUTORIZADO':
        comp.estado = Comprobante.ESTADO_RECHAZADA
        comp.mensajes = '; '.join(resp['mensajes']) or 'Comprobante no autorizado.'
        comp.save(update_fields=['estado', 'mensajes', 'actualizado'])
        _log(comp, LogSri.NIVEL_ERROR,
             f'No autorizado: {comp.mensajes}')
    else:
        _log(comp, LogSri.NIVEL_INFO,
             f'Autorización en proceso ("{estado}"), se reintentará luego.')


def reenviar_pendientes(consultar=True):
    """Reintenta los comprobantes pendientes y consulta los enviados.

    Usado por el comando `facturacion_pendientes`. Devuelve tupla con
    (reintentados, consultados).
    """
    reintentados = 0
    for comp in Comprobante.objects.filter(
        estado=Comprobante.ESTADO_PENDIENTE
    ).select_related('pedido'):
        try:
            _enviar_y_autorizar(comp)
        except Exception:  # noqa: BLE001
            logger.exception('Reintento fallido de %s', comp.numero_completo)
        reintentados += 1

    consultados = 0
    if consultar:
        emisor = EmisorConfig.obtener()
        for comp in Comprobante.objects.filter(estado=Comprobante.ESTADO_ENVIADA):
            try:
                _consultar_autorizacion(comp, emisor)
            except Exception:  # noqa: BLE001
                logger.exception('Consulta fallida de %s', comp.numero_completo)
            consultados += 1
    return reintentados, consultados


def total_pendiente_monto():
    """Suma de pedidos de comprobantes no autorizados (útil para alertas)."""
    total = Decimal('0.00')
    for comp in Comprobante.objects.filter(
        estado__in=(Comprobante.ESTADO_PENDIENTE, Comprobante.ESTADO_ENVIADA)
    ).select_related('pedido'):
        total += comp.pedido.total
    return total
