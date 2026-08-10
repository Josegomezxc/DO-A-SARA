"""Clave de acceso de comprobantes electrónicos (SRI Ecuador).

La clave tiene 49 dígitos (Ficha técnica SRI, esquema offline):
  - 8: fecha de emisión (ddmmaaaa)
  - 2: tipo de comprobante (01 = factura)
  - 13: RUC del emisor
  - 1: tipo de ambiente (1 pruebas / 2 producción)
  - 6: establecimiento + punto de emisión (001001)
  - 9: secuencial
  - 8: código numérico (aleatorio)
  - 1: tipo de emisión (1 normal / 2 contingencia)
  - 1: dígito verificador (módulo 11 sobre los 48 primeros)
"""
from datetime import date

TIPO_FACTURA = '01'
TIPO_EMISION_NORMAL = '1'


def digito_verificador_modulo11(cadena):
    """Calcula el dígito verificador con el algoritmo del SRI.

    Pesos 2..7 desde el dígito más a la derecha; si el resultado es
    11 queda en 0 y si es 10 queda en 1.
    """
    pesos = [2, 3, 4, 5, 6, 7]
    suma = 0
    peso_idx = 0
    for digito in reversed(cadena):
        if not digito.isdigit():
            raise ValueError('La clave solo admite dígitos.')
        suma += int(digito) * pesos[peso_idx % len(pesos)]
        peso_idx += 1
    digito = 11 - (suma % 11)
    if digito == 11:
        digito = 0
    elif digito == 10:
        digito = 1
    return str(digito)


def generar_clave_acceso(fecha, ruc, ambiente, serie, secuencial,
                         codigo_numerico, tipo_comprobante=TIPO_FACTURA,
                         tipo_emision=TIPO_EMISION_NORMAL):
    """Genera la clave de acceso de 49 dígitos según la ficha técnica.

    `fecha` es date/datetime, `ambiente` es '1' (pruebas) o '2'
    (producción), `serie` es establecimiento+punto (6 dígitos),
    `secuencial` es int (se formatea a 9) y `codigo_numerico` es un
    string de 8 dígitos.
    """
    if isinstance(fecha, str):
        raise ValueError('fecha debe ser date o datetime')
    cuerpo = (
        f'{fecha:%d%m%Y}'
        f'{str(tipo_comprobante)}'
        f'{str(ruc):>013}'
        f'{str(ambiente):>01}'
        f'{str(serie):>06}'
        f'{int(secuencial):09d}'
        f'{str(codigo_numerico):>08}'
        f'{str(tipo_emision):>01}'
    )
    if len(cuerpo) != 48:
        raise ValueError(f'El cuerpo de la clave debe tener 48 dígitos (tiene {len(cuerpo)}).')
    return cuerpo + digito_verificador_modulo11(cuerpo)


def validar_clave_acceso(clave):
    """Devuelve True si la clave tiene 49 dígitos y el verificador cuadra."""
    if len(clave) != 49 or not clave.isdigit():
        return False
    return digito_verificador_modulo11(clave[:48]) == clave[-1]
