"""PDF A4 de la factura electrónica (reportlab).

Genera el documento imprimible del comprobante con los mismos datos
que el XML del SRI: emisor, receptor, detalle con precios (incluyen
IVA, como el ticket) y desglose de totales. Si el comprobante está
autorizado, incluye el número y la fecha de autorización.
"""
import html
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)

from app.facturacion.models import Comprobante, EmisorConfig
from app.orders.models import Order

# ---------- Estilos ----------

AZUL = colors.HexColor('#2563EB')

STILO_EMISOR = ParagraphStyle(
    'emisor', fontName='Helvetica-Bold', fontSize=15, leading=18,
    textColor=AZUL,
)
STILO_LABEL = ParagraphStyle(
    'label', fontName='Helvetica-Bold', fontSize=8, leading=10,
    textColor=colors.grey,
)
STILO_DATO = ParagraphStyle(
    'dato', fontName='Helvetica', fontSize=10, leading=13,
)
STILO_CLAVE = ParagraphStyle(
    'clave', fontName='Helvetica', fontSize=9, leading=12,
)
STILO_TITULO_SECCION = ParagraphStyle(
    'titulo', fontName='Helvetica-Bold', fontSize=10, leading=13,
)
STILO_CELDA = ParagraphStyle(
    'celda', fontName='Helvetica', fontSize=9, leading=11,
)
STILO_CELDA_BOLD = ParagraphStyle(
    'celda_bold', fontName='Helvetica-Bold', fontSize=9, leading=11,
)
STILO_CELDA_CENTER = ParagraphStyle(
    'celda_center', fontName='Helvetica', fontSize=9, leading=11,
    alignment=TA_CENTER,
)
STILO_CABECERA = ParagraphStyle(
    'cabecera', fontName='Helvetica-Bold', fontSize=9, leading=11,
    textColor=colors.white,
    alignment=TA_CENTER,
)
STILO_TOTAL = ParagraphStyle(
    'total', fontName='Helvetica-Bold', fontSize=13, leading=16,
)
STILO_AUTORIZADO = ParagraphStyle(
    'autorizado', fontName='Helvetica-Bold', fontSize=9, leading=12,
    textColor=colors.HexColor('#15803d'),
)
STILO_PIE = ParagraphStyle(
    'pie', fontName='Helvetica', fontSize=7, leading=9,
    textColor=colors.grey, alignment=TA_CENTER,
)


def _par(texto, estilo):
    return Paragraph(html.escape(str(texto or '')), estilo)


def _moneda(valor):
    return f'$ {Decimal(str(valor or 0)).quantize(Decimal("0.01")):,.2f}'


def _fecha(dt):
    return dt.strftime('%d/%m/%Y') if dt else ''


def _tipo_identificacion(tipo):
    return dict(Order.TIPO_IDENTIFICACION_CHOICES).get(tipo, tipo or '')


def _ambientar(emisor):
    return 'Pruebas' if emisor.ambiente == EmisorConfig.AMBIENTE_PRUEBAS else 'Producción'


def generar_pdf(comp):
    """Devuelve los bytes del PDF A4 del comprobante."""
    emisor = EmisorConfig.obtener()
    pedido = comp.pedido

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
    )

    def pie(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(
            A4[0] / 2, 8 * mm,
            f'Clave de acceso: {comp.clave_acceso}  ·  Página {doc_.page}',
        )
        canvas.restoreState()

    doc.addPageTemplates([
        PageTemplate(id='pagina', frames=[
            Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='cuerpo'),
        ], onPage=pie),
    ])

    story = []

    # ---------- Encabezado del emisor ----------
    story.append(_par(emisor.razon_social, STILO_EMISOR))
    story.append(Spacer(1, 1 * mm))
    story.append(_par(f'R.U.C.: {emisor.ruc}', STILO_DATO))
    lineas_emisor = [emisor.direccion]
    if emisor.telefono:
        lineas_emisor.append(f'Tel.: {emisor.telefono}')
    if emisor.email:
        lineas_emisor.append(emisor.email)
    story.append(_par(' · '.join(l for l in lineas_emisor if l), STILO_CLAVE))
    story.append(Spacer(1, 3 * mm))

    # ---------- Datos del documento ----------
    cabecera = Table(
        [[_par('FACTURA ELECTRÓNICA', STILO_EMISOR),
          Table([
              [_par('NÚMERO', STILO_LABEL), _par(comp.numero, STILO_DATO)],
              [_par('FECHA DE EMISIÓN', STILO_LABEL), _par(_fecha(pedido.creado), STILO_DATO)],
              [_par('AMBIENTE', STILO_LABEL), _par(_ambientar(emisor), STILO_DATO)],
          ], colWidths=[36 * mm, 62 * mm])]],
        colWidths=[doc.width - 98 * mm, 98 * mm],
    )
    cabecera.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (0, 0), 0.5, AZUL),
    ]))
    story.append(cabecera)
    story.append(Spacer(1, 1 * mm))
    story.append(_par(f'Clave de acceso: {comp.clave_acceso}', STILO_CLAVE))
    story.append(Spacer(1, 3 * mm))

    # ---------- Receptor ----------
    story.append(_par('DATOS DEL RECEPTOR', STILO_TITULO_SECCION))
    story.append(Spacer(1, 1.5 * mm))
    nombre_cliente = (pedido.cliente or '').strip() or 'CONSUMIDOR FINAL'
    datos_receptor = [[
        _par('IDENTIFICACIÓN', STILO_LABEL),
        _par('NOMBRE', STILO_LABEL),
    ], [
        _par(f'{_tipo_identificacion(pedido.tipo_identificacion)}: '
             f'{pedido.identificacion or ""}', STILO_DATO),
        _par(nombre_cliente, STILO_DATO),
    ]]
    if pedido.direccion or pedido.telefono or pedido.email:
        datos_receptor.append([
            _par('', STILO_DATO),
            _par(
                ' · '.join(l for l in (
                    pedido.direccion,
                    f'Tel.: {pedido.telefono}' if pedido.telefono else '',
                    pedido.email or '',
                ) if l),
                STILO_CLAVE,
            ),
        ])
    tabla_receptor = Table(datos_receptor, colWidths=[46 * mm, doc.width - 46 * mm])
    tabla_receptor.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(tabla_receptor)
    story.append(Spacer(1, 4 * mm))

    # ---------- Detalle ----------
    story.append(_par('DETALLE', STILO_TITULO_SECCION))
    story.append(Spacer(1, 1.5 * mm))
    filas = [[
        _par('CÓDIGO', STILO_CABECERA),
        _par('DESCRIPCIÓN', STILO_CABECERA),
        _par('CANT.', STILO_CABECERA),
        _par('P. UNIT', STILO_CABECERA),
        _par('DESC.', STILO_CABECERA),
        _par('TOTAL', STILO_CABECERA),
    ]]
    for item in pedido.items.select_related('producto'):
        filas.append([
            _par(item.producto_id or '', STILO_CELDA_CENTER),
            _par(item.producto.nombre, STILO_CELDA),
            _par(f'{Decimal(str(item.cantidad)):.0f}', STILO_CELDA_CENTER),
            _par(_moneda(item.precio_unitario), STILO_CELDA_CENTER),
            _par('', STILO_CELDA_CENTER),
            _par(_moneda(item.subtotal), STILO_CELDA_CENTER),
        ])
    ancho_detalle = doc.width
    tabla_detalle = Table(
        filas,
        colWidths=[0.13 * ancho_detalle, 0.39 * ancho_detalle,
                   0.08 * ancho_detalle, 0.15 * ancho_detalle,
                   0.10 * ancho_detalle, 0.15 * ancho_detalle],
        repeatRows=1,
    )
    tabla_detalle.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tabla_detalle)
    story.append(Spacer(1, 4 * mm))

    # ---------- Totales ----------
    iva_pct = f'{Decimal(str(pedido.iva_alicuota)) * 100:.0f}'
    filas_totales = [
        [_par('Subtotal (sin IVA)', STILO_CELDA), _par(_moneda(pedido.subtotal_sin_iva), STILO_CELDA)],
        [_par(f'IVA ({iva_pct}%)', STILO_CELDA), _par(_moneda(pedido.iva_subtotal), STILO_CELDA)],
        [_par('Subtotal', STILO_CELDA_BOLD), _par(_moneda(pedido.subtotal), STILO_CELDA_BOLD)],
    ]
    if pedido.descuento:
        filas_totales.append(
            [_par('Descuento', STILO_CELDA), _par(f'- {_moneda(pedido.descuento)}', STILO_CELDA)]
        )
    filas_totales.append(
        [_par('TOTAL', STILO_TOTAL), _par(_moneda(pedido.total), STILO_TOTAL)]
    )
    if pedido.metodo_pago:
        filas_totales.append(
            [_par('Forma de pago', STILO_CELDA),
             _par(pedido.get_metodo_pago_display(), STILO_CELDA)]
        )
    tabla_totales = Table(filas_totales, colWidths=[52 * mm, 34 * mm])
    tabla_totales.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 0.75, AZUL),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    tabla_totales.hAlign = 'RIGHT'
    story.append(tabla_totales)
    story.append(Spacer(1, 4 * mm))

    # ---------- Autorización ----------
    if comp.estado == Comprobante.ESTADO_AUTORIZADA:
        filas_auth = [
            [_par('NÚMERO DE AUTORIZACIÓN', STILO_LABEL),
             _par(comp.numero_autorizacion, STILO_AUTORIZADO)],
            [_par('FECHA DE AUTORIZACIÓN', STILO_LABEL),
             _par(_fecha(comp.actualizado), STILO_AUTORIZADO)],
        ]
        tabla_auth = Table(filas_auth, colWidths=[52 * mm, doc.width - 52 * mm])
        tabla_auth.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#15803d')),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(tabla_auth)
        story.append(Spacer(1, 4 * mm))

    # ---------- Info adicional ----------
    adicional = []
    if pedido.direccion:
        adicional.append(f'Dirección: {pedido.direccion}')
    if pedido.telefono:
        adicional.append(f'Teléfono: {pedido.telefono}')
    if pedido.email:
        adicional.append(f'Email: {pedido.email}')
    if pedido.vendedor:
        nombre_vendedor = pedido.vendedor.get_full_name() or pedido.vendedor.username
        adicional.append(f'Vendedor: {nombre_vendedor}')
    if pedido.notas:
        adicional.append(f'Notas: {pedido.notas}')
    if adicional:
        story.append(_par('INFORMACIÓN ADICIONAL', STILO_TITULO_SECCION))
        story.append(Spacer(1, 1.5 * mm))
        for linea in adicional:
            story.append(_par(linea, STILO_CLAVE))

    story.append(Spacer(1, 6 * mm))
    story.append(_par(
        'Documento generado electrónicamente. Verifíquelo en la web del SRI '
        'con la clave de acceso. Precios incluyen IVA.',
        STILO_PIE,
    ))

    doc.build(story)
    return buf.getvalue()
