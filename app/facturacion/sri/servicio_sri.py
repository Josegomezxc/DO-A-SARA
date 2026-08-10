"""Servicio SOAP del SRI (Recepción y Autorización de comprobantes).

Usa zeep contra el WSDL oficial. El ambiente (pruebas/producción) se
toma de `EmisorConfig.ambiente`.
"""
import logging
import time

logger = logging.getLogger(__name__)

WSDL_RECEPCION = {
    '1': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
    '2': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline?wsdl',
}
WSDL_AUTORIZACION = {
    '1': 'https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
    '2': 'https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl',
}

TIMEOUT = 45
REINTENTOS = 2

_clientes = {}


def _cliente(wsdl, ambiente):
    """Cliente zeep en cache (evita re-descargar el WSDL en cada llamada)."""
    key = (ambiente, wsdl)
    if key not in _clientes:
        from zeep import Client
        from zeep.transports import Transport

        transport = Transport(timeout=TIMEOUT, operation_timeout=TIMEOUT)
        _clientes[key] = Client(wsdl, transport=transport)
    return _clientes[key]


def _get(obj, nombre, default=None):
    """Acceso tolerante a un campo: soporta dicts y objetos zeep.

    Los objetos que devuelve zeep (CompoundValue) no tienen `.get()`:
    los campos se acceden como atributos. Los wrappers de respuesta
    (RespuestaRecepcionComprobante / RespuestaAutorizacionComprobante)
    se aplanan: si el campo no está en el nivel superior, se busca en
    el wrapper anidado.
    """
    if hasattr(obj, 'get'):
        valor = obj.get(nombre)
        if valor is not None:
            return valor
    else:
        try:
            valor = getattr(obj, nombre, None)
            if valor is not None:
                return valor
        except (AttributeError, TypeError):
            pass
    for wrapper in ('RespuestaRecepcionComprobante', 'RespuestaAutorizacionComprobante'):
        if hasattr(obj, 'get'):
            anidado = obj.get(wrapper)
        else:
            anidado = getattr(obj, wrapper, None)
        if anidado is not None and anidado is not obj:
            if hasattr(anidado, 'get'):
                valor = anidado.get(nombre)
                if valor is not None:
                    return valor
            else:
                try:
                    valor = getattr(anidado, nombre, None)
                    if valor is not None:
                        return valor
                except (AttributeError, TypeError):
                    pass
    return default


def _lista_de(valor):
    """Normaliza a lista: dict -> [dict], None -> [], list -> list."""
    if isinstance(valor, dict) or hasattr(valor, 'keys'):
        return [valor]
    return list(valor or [])


def _mensajes_de(respuesta):
    """Extrae los mensajes SRI de una respuesta zeep (dict-like).

    Soporta ambos shapes: recepción
    (comprobantes.comprobante[].mensajes.mensaje[]) y autorización
    (autorizaciones.autorizacion[].mensajes.mensaje[]).
    """
    mensajes = []
    try:
        candidatos = []
        comprobantes = _get(respuesta, 'comprobantes') or {}
        candidatos.extend(_lista_de(_get(comprobantes, 'comprobante')))
        autores = _get(respuesta, 'autorizaciones') or {}
        candidatos.extend(_lista_de(_get(autores, 'autorizacion')))
        for comp in candidatos:
            m = _get(comp, 'mensajes') or {}
            lista_m = _lista_de(_get(m, 'mensaje'))
            for msj in lista_m:
                adicional = _get(msj, 'informacionAdicional')
                if adicional:
                    texto = f"{_get(msj, 'identificador', '')}: {_get(msj, 'mensaje', '')} " \
                            f"[{_get(msj, 'tipo', '')}] — {adicional}"
                else:
                    texto = f"{_get(msj, 'identificador', '')}: {_get(msj, 'mensaje', '')} " \
                            f"[{_get(msj, 'tipo', '')}]"
                mensajes.append(texto)
    except Exception:  # noqa: BLE001 — nunca romper por parseo
        logger.exception('No se pudo parsear mensajes del SRI')
    return mensajes


def _con_reintentos(func):
    def wrapper(*args, **kwargs):
        ultimo_error = None
        for intento in range(1, REINTENTOS + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                ultimo_error = exc
                logger.warning('Intento %s fallido: %s', intento, exc)
                if intento < REINTENTOS:
                    time.sleep(2 * intento)
        raise ultimo_error
    return wrapper


@_con_reintentos
def enviar(xml_firmado, ambiente):
    """Envía el XML firmado a Recepción. Devuelve dict con estado y mensajes."""
    datos = xml_firmado.encode('utf-8') if isinstance(xml_firmado, str) else xml_firmado
    cliente = _cliente(WSDL_RECEPCION[ambiente], ambiente)
    # El WSDL de Recepción define el parámetro como `xml` (base64Binary)
    respuesta = cliente.service.validarComprobante(xml=datos)
    estado = str(_get(respuesta, 'estado', '') or '').upper()
    return {
        'estado': estado,
        'mensajes': _mensajes_de(respuesta),
        'numero_autorizacion': '',
        'xml_autorizado': '',
    }


@_con_reintentos
def consultar_autorizacion(clave_acceso, ambiente):
    """Consulta la autorización de un comprobante. Devuelve dict."""
    cliente = _cliente(WSDL_AUTORIZACION[ambiente], ambiente)
    respuesta = cliente.service.autorizacionComprobante(
        claveAccesoComprobante=clave_acceso
    )
    estado = str(_get(respuesta, 'estado', '') or '').upper()

    numero = ''
    xml_autorizado = ''
    try:
        autores = _get(respuesta, 'autorizaciones') or {}
        auths = _lista_de(_get(autores, 'autorizacion'))
        if auths:
            primera = auths[0]
            numero = str(_get(primera, 'numeroAutorizacion', '') or '')
            estado = str(_get(primera, 'estado', '') or '').upper() or estado
            import base64
            import zlib
            xml_b64 = _get(primera, 'comprobante') or ''
            if xml_b64:
                try:
                    xml_autorizado = zlib.decompress(
                        base64.b64decode(xml_b64), -zlib.MAX_WBITS
                    ).decode('utf-8')
                except Exception:  # noqa: BLE001
                    try:
                        xml_autorizado = zlib.decompress(
                            base64.b64decode(xml_b64)
                        ).decode('utf-8')
                    except Exception:  # noqa: BLE001
                        xml_autorizado = ''
    except Exception:  # noqa: BLE001
        logger.exception('No se pudo parsear la autorización')

    return {
        'estado': estado,
        'mensajes': _mensajes_de(respuesta),
        'numero_autorizacion': numero,
        'xml_autorizado': xml_autorizado,
    }
