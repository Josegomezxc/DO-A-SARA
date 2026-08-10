"""Validación de identificaciones ecuatorianas (SRI).

Algoritmos oficiales:
  - Cédula: 10 dígitos, provincia 01-24, 3er dígito 0-5, módulo 10
    con pesos [2,1,2,1,2,1,2,1,2] (producto >= 10 se resta 9).
  - RUC: 13 dígitos; el 3er dígito define el tipo:
      * 6  -> sector público (módulo 11, pesos 3,2,7,6,5,4,3,2)
      * 9  -> persona jurídica (módulo 11, pesos 4,3,2,7,6,5,4,3,2)
      * 0-5 -> persona natural (los 10 primeros son una cédula válida)
      * 7-8 -> inválido
  - Pasaporte: 5 a 20 caracteres alfanuméricos (sin espacios ni símbolos).
"""
import re

PASAPORTE_RE = re.compile(r'^[A-Za-z0-9]+$')


def _digito_modulo10(cedula):
    """Dígito verificador de la cédula (módulo 10) o None si el formato no aplica."""
    if len(cedula) != 10 or not cedula.isdigit():
        return None
    pesos = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    suma = 0
    for digito, peso in zip(cedula[:9], pesos):
        producto = int(digito) * peso
        suma += producto - 9 if producto >= 10 else producto
    return str((10 - (suma % 10)) % 10)


def _digito_modulo11(primeros_9, pesos):
    """Dígito verificador de RUC (módulo 11); 0 y 1 quedan como están."""
    suma = sum(int(d) * p for d, p in zip(primeros_9, pesos))
    residuo = suma % 11
    if residuo == 0:
        return '0'
    if residuo == 1:
        return '1'
    return str(11 - residuo)


def es_cedula_valida(cedula):
    """True si `cedula` es una cédula ecuatoriana válida."""
    if not cedula or not cedula.isdigit() or len(cedula) != 10:
        return False
    provincia = int(cedula[:2])
    if not (1 <= provincia <= 24):
        return False
    if cedula[2] not in '012345':
        return False
    return _digito_modulo10(cedula) == cedula[-1]


def es_ruc_valido(ruc):
    """True si `ruc` es un RUC ecuatoriano válido (natural, jurídico o público)."""
    if not ruc or not ruc.isdigit() or len(ruc) != 13:
        return False
    tercero = ruc[2]
    if tercero == '9':  # persona jurídica
        return _digito_modulo11(ruc[:9], [4, 3, 2, 7, 6, 5, 4, 3, 2]) == ruc[9]
    if tercero == '6':  # sector público
        return _digito_modulo11(ruc[:9], [3, 2, 7, 6, 5, 4, 3, 2]) == ruc[9]
    if tercero in '012345':  # persona natural
        return es_cedula_valida(ruc[:10]) and int(ruc[10:]) >= 1
    return False


def es_pasaporte_valido(pasaporte):
    """True si `pasaporte` tiene 5-20 caracteres alfanuméricos."""
    if not pasaporte:
        return False
    return 5 <= len(pasaporte) <= 20 and bool(PASAPORTE_RE.match(pasaporte))


def validar_identificacion(tipo, numero):
    """Valida `numero` según el `tipo` de identificación.

    `tipo` usa los códigos del SRI: '04' RUC, '05' cédula, '06' pasaporte.
    Devuelve una lista de mensajes de error (vacía si es válido).
    """
    numero = (numero or '').strip()
    if tipo == '04':
        if not numero:
            return ['El número de identificación es obligatorio.']
        if len(numero) != 13 or not numero.isdigit():
            return ['El RUC debe tener 13 dígitos.']
        if not es_ruc_valido(numero):
            return ['El RUC no es válido (dígito verificador incorrecto).']
    elif tipo == '05':
        if not numero:
            return ['El número de identificación es obligatorio.']
        if len(numero) != 10 or not numero.isdigit():
            return ['La cédula debe tener 10 dígitos.']
        if not es_cedula_valida(numero):
            return ['La cédula no es válida (dígito verificador incorrecto).']
    elif tipo == '06':
        if not numero:
            return ['El número de identificación es obligatorio.']
        if not es_pasaporte_valido(numero):
            if not PASAPORTE_RE.match(numero):
                return ['El pasaporte solo puede contener letras y números.']
            return ['El pasaporte tiene un largo inválido.']
    return []


# ---------- Nombres (normalización de espacios) ----------

def normalizar_nombre(valor):
    """Normaliza un nombre: recorta bordes, colapsa espacios y arregla
    letras sueltas tipeadas con espacios raros.

    Reglas (espejo de validacion.js):
      - Letras sueltas AISLADAS (1 sola letra entre palabras reales) se
        conservan como palabra separada: "Hamburguesa a lo especial".
      - Grupos de 2+ letras sueltas seguidas (basura tipada) se unen entre
        sí y se pegan a la palabra anterior (o quedan como palabra al inicio):
        "ca      m   i s a s" -> "camisas".
    """
    tokens = re.split(r'\s+', (valor or '').strip())
    tokens = [t for t in tokens if t]
    if not tokens:
        return ''

    out = []
    run = ''
    run_count = 0

    def cerrar_run():
        nonlocal run, run_count
        if not run:
            return
        if run_count == 1 and out:
            out.append(run)          # letra suelta aislada: queda como palabra
        elif out:
            out[-1] += run           # basura de 2+: se pega a la anterior
        else:
            out.append(run)
        run = ''
        run_count = 0

    for t in tokens:
        if len(t) == 1:
            run += t
            run_count += 1
        else:
            cerrar_run()
            out.append(t)
    cerrar_run()
    return ' '.join(out)


def errores_nombre(valor):
    """Devuelve una lista de errores para un nombre ya normalizado
    (vacía si es válido)."""
    nombre = normalizar_nombre(valor)
    if not nombre:
        return ['El nombre es obligatorio.']
    return []


# ---------- Montos (precio, descuento, recibido) ----------

def errores_monto(valor, *, max_int=10):
    """Devuelve una lista de errores para un monto en dinero.

    `valor` debe ser un Decimal. Valida: no negativo, máximo 2 decimales
    y máximo `max_int` dígitos enteros.
    """
    from decimal import Decimal

    errores = []
    if valor is None:
        return ['Ingresá un monto válido.']
    if valor < 0:
        errores.append('El monto no puede ser negativo.')
    if valor.as_tuple().exponent < -2:
        errores.append('El monto no puede tener más de 2 decimales.')
    if abs(valor) >= Decimal(10) ** max_int:
        errores.append(
            f'El monto no puede superar los {max_int} dígitos enteros.'
        )
    return errores
