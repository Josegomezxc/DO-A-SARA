"""Construcción del XML de factura electrónica (XSD 2.1.0, SRI).

Los precios del POS incluyen IVA; el XML del SRI exige precios y
descuentos SIN impuestos. Cada línea se convierte a espacio sin IVA
(precio / (1 + alícuota), a 4 decimales) y el descuento se reparte
proporcionalmente también sin IVA. El redondeo sobrante se ajusta en
la última línea para que los totales cuadren al centavo y cada línea
cumpla la validación de montos del SRI
(|precioUnitario * cantidad - descuento - precioTotalSinImpuesto| <= 0.01).
"""
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from lxml import etree

# Mapeo alícuota % -> código de porcentaje del SRI (catálogo vigente,
# ficha técnica 2.28): 15% = 4, 14% = 3, 13% = 10, 12% = 2, 8% = 8,
# 5% = 5 (construcción), 0% = 0. El 6 es "No objeto de IVA" y no
# corresponde a ninguna tarifa gravada.
PORCENTAJE_A_CODIGO = {
    '0': '0', '5': '5', '8': '8', '12': '2',
    '13': '10', '14': '3', '15': '4',
}
# Tarifa general vigente (13%) como red para alícuotas no mapeadas.
PORCENTAJE_DEFAULT = '10'

# Formas de pago (catálogo SRI).
FORMA_PAGO = {
    'efectivo': '01',
    'tarjeta': '19',
    'transferencia': '20',
    'qr': '20',
}
FORMA_PAGO_DEFAULT = '01'

IDENTIFICACION_DEFAULT = '9999999999999'
TIPO_IDENTIFICACION_DEFAULT = '07'


def _dec(valor):
    return Decimal(str(valor or '0'))


def _red(valor):
    return _dec(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _tarifa_porcentaje(rate):
    pct = str(int(round(float(_dec(rate)) * 100)))
    return PORCENTAJE_A_CODIGO.get(pct, PORCENTAJE_DEFAULT)


def _el(parent, tag, text=None, **attrs):
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def _detalles_con_descuento(items, descuento, divisor):
    """Calcula las líneas de detalle en espacio SIN IVA.

    Devuelve lista de dicts con: cantidad, precio_unitario (sin IVA a
    4 decimales), descuento, base (sin IVA), valor_iva, descripcion,
    codigo. El descuento (ya convertido a sin IVA) se reparte
    proporcionalmente al bruto sin IVA de cada línea y el redondeo se
    absorbe en la última.
    """
    lineas = []
    subtotal = Decimal('0.00')
    for item in items:
        cantidad = _dec(item.cantidad)
        unit_sin = (_dec(item.precio_unitario) / divisor).quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        )
        bruto = (unit_sin * cantidad).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        subtotal += bruto
        lineas.append({'item': item, 'bruto': bruto, 'unit_sin': unit_sin})

    resto_desc = _dec(descuento)
    for i, linea in enumerate(lineas):
        if i == len(lineas) - 1:
            linea['descuento'] = resto_desc
        else:
            d = (linea['bruto'] * resto_desc / subtotal).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            ) if subtotal else Decimal('0.00')
            linea['descuento'] = min(d, resto_desc)
            resto_desc -= linea['descuento']
    return lineas


def construir_xml(emisor, pedido, clave_acceso, secuencial, numero_completo,
                  fecha_emision=None):
    """Devuelve el XML sin firmar como bytes (encoding utf-8).

    `fecha_emision` debe ser la MISMA fecha usada en la clave de acceso
    (fecha local de emisión). Si es None se usa la fecha local de
    creación del pedido (compatibilidad con llamadas antiguas).
    """
    rate = pedido.iva_alicuota
    divisor = Decimal('1') + _dec(rate)
    codigo_pct = _tarifa_porcentaje(rate)

    # Descuento en espacio sin IVA (el pedido lo guarda con IVA incluido).
    descuento_sin = (_dec(pedido.descuento) / divisor).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )

    lineas = _detalles_con_descuento(
        pedido.items.select_related('producto').all(), descuento_sin, divisor,
    )

    # Base por línea: bruto sin IVA redondeado al centavo menos su descuento.
    for linea in lineas:
        linea['base'] = linea['bruto'] - linea['descuento']

    total_sin_impuestos = sum((l['base'] for l in lineas), Decimal('0.00'))
    total_descuento = sum((l['descuento'] for l in lineas), Decimal('0.00'))

    valor_iva = (total_sin_impuestos * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    # Ajuste al centavo: importeTotal debe ser exactamente el total del pedido.
    importe = total_sin_impuestos + valor_iva
    if importe != _dec(pedido.total):
        valor_iva += _dec(pedido.total) - importe

    # IVA por línea; la última absorbe la diferencia de redondeo.
    for i, linea in enumerate(lineas):
        v = (linea['base'] * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        linea['valor_iva'] = v
    resto_iva = valor_iva - sum((l['valor_iva'] for l in lineas), Decimal('0.00'))
    if lineas:
        lineas[-1]['valor_iva'] += resto_iva

    cliente = (pedido.cliente or '').strip() or 'CONSUMIDOR FINAL'
    tipo_ident = pedido.tipo_identificacion or TIPO_IDENTIFICACION_DEFAULT
    ident = (pedido.identificacion or '').strip() or IDENTIFICACION_DEFAULT

    # ---------- Árbol XML ----------
    raiz = etree.Element('factura', id='comprobante', version='2.1.0')

    info_tributaria = etree.SubElement(raiz, 'infoTributaria')
    _el(info_tributaria, 'ambiente', emisor.ambiente)
    _el(info_tributaria, 'tipoEmision', '1')
    _el(info_tributaria, 'razonSocial', emisor.razon_social)
    if emisor.nombre_comercial:
        _el(info_tributaria, 'nombreComercial', emisor.nombre_comercial)
    _el(info_tributaria, 'ruc', emisor.ruc)
    _el(info_tributaria, 'claveAcceso', clave_acceso)
    _el(info_tributaria, 'codDoc', '01')
    _el(info_tributaria, 'estab', emisor.establecimiento)
    _el(info_tributaria, 'ptoEmi', emisor.punto_emision)
    _el(info_tributaria, 'secuencial', f'{int(secuencial):09d}')
    _el(info_tributaria, 'dirMatriz', emisor.direccion)
    if emisor.agente_retencion:
        _el(info_tributaria, 'agenteRetencion', '1')

    info_factura = etree.SubElement(raiz, 'infoFactura')
    fecha = fecha_emision or timezone.localtime(pedido.creado).date()
    _el(info_factura, 'fechaEmision', f'{fecha:%d/%m/%Y}')
    _el(info_factura, 'dirEstablecimiento', emisor.direccion)
    if emisor.contribuyente_especial:
        _el(info_factura, 'contribuyenteEspecial', emisor.contribuyente_especial)
    _el(info_factura, 'obligadoContabilidad',
        'SI' if emisor.obligado_contabilidad else 'NO')
    _el(info_factura, 'tipoIdentificacionComprador', tipo_ident)
    _el(info_factura, 'razonSocialComprador', cliente)
    _el(info_factura, 'identificacionComprador', ident)
    if pedido.direccion:
        _el(info_factura, 'direccionComprador', pedido.direccion)
    _el(info_factura, 'totalSinImpuestos', f'{total_sin_impuestos:.2f}')
    _el(info_factura, 'totalDescuento', f'{total_descuento:.2f}')

    total_con_impuestos = etree.SubElement(info_factura, 'totalConImpuestos')
    total_impuesto = etree.SubElement(total_con_impuestos, 'totalImpuesto')
    _el(total_impuesto, 'codigo', '2')
    _el(total_impuesto, 'codigoPorcentaje', codigo_pct)
    _el(total_impuesto, 'descuentoAdicional', '0.00')
    _el(total_impuesto, 'baseImponible', f'{total_sin_impuestos:.2f}')
    _el(total_impuesto, 'valor', f'{valor_iva:.2f}')

    _el(info_factura, 'propina', '0.00')
    _el(info_factura, 'importeTotal', f'{_dec(pedido.total):.2f}')
    _el(info_factura, 'moneda', 'DOLAR')

    pagos = etree.SubElement(info_factura, 'pagos')
    pago = etree.SubElement(pagos, 'pago')
    _el(pago, 'formaPago', FORMA_PAGO.get(pedido.metodo_pago, FORMA_PAGO_DEFAULT))
    _el(pago, 'total', f'{_dec(pedido.total):.2f}')

    detalles = etree.SubElement(raiz, 'detalles')
    for linea in lineas:
        detalle = etree.SubElement(detalles, 'detalle')
        _el(detalle, 'codigoPrincipal', str(linea['item'].producto_id or ''))
        _el(detalle, 'descripcion', linea['item'].producto.nombre)
        _el(detalle, 'cantidad', f'{int(linea["item"].cantidad)}')
        _el(detalle, 'precioUnitario', f'{linea["unit_sin"]:.4f}')
        _el(detalle, 'descuento', f'{_dec(linea["descuento"]):.2f}')
        _el(detalle, 'precioTotalSinImpuesto', f'{_dec(linea["base"]):.2f}')
        impuestos = etree.SubElement(detalle, 'impuestos')
        impuesto = etree.SubElement(impuestos, 'impuesto')
        _el(impuesto, 'codigo', '2')
        _el(impuesto, 'codigoPorcentaje', codigo_pct)
        _el(impuesto, 'tarifa', f'{int(round(float(_dec(rate)) * 100))}')
        _el(impuesto, 'baseImponible', f'{_dec(linea["base"]):.2f}')
        _el(impuesto, 'valor', f'{_dec(linea["valor_iva"]):.2f}')

    info_adicional = etree.SubElement(raiz, 'infoAdicional')
    campos = [
        ('Dirección', pedido.direccion),
        ('Teléfono', pedido.telefono),
        ('Email', pedido.email),
        ('Vendedor', pedido.vendedor.get_full_name() or pedido.vendedor.username),
        ('Método de pago', pedido.get_metodo_pago_display()),
    ]
    for nombre, valor in campos:
        if valor:
            _el(info_adicional, 'campoAdicional', valor, nombre=nombre)

    return etree.tostring(raiz, xml_declaration=True, encoding='UTF-8', pretty_print=False)
