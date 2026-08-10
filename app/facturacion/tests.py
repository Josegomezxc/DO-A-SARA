"""Tests de facturación electrónica SRI."""
import json
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import mock
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from lxml import etree

from app.orders.models import Order, OrderItem
from app.products.models import Category, Product
from app.users.models import Profile

from .models import Comprobante, EmisorConfig, LogSri
from .forms import EmisorConfigForm
from .sri import emision as sri_emision
from .sri import servicio_sri as sri_servicio
from .sri.clave_acceso import (
    digito_verificador_modulo11, generar_clave_acceso, validar_clave_acceso,
)
from .sri.xml_builder import construir_xml

MEDIA_TMP = tempfile.mkdtemp(prefix='facturacion_test_media_')


def _crear_p12(destino, ruc='1710034065001'):
    """Genera un .p12 autofirmado de prueba en `destino`.

    Por defecto embebe el RUC en el sujeto (como las firmas reales del
    SRI); con `ruc=None` se genera sin RUC (equivale a una firma no apta).
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'EC'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'TEST'),
        x509.NameAttribute(NameOID.COMMON_NAME, 'TEST SRI'),
    ]
    if ruc is not None:
        attrs.append(x509.NameAttribute(NameOID.SERIAL_NUMBER, f'RUC: {ruc}'))
    subject = x509.Name(attrs)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(datetime(2030, 1, 1, tzinfo=timezone.utc))
        .sign(key, hashes.SHA256())
    )
    p12 = pkcs12.serialize_key_and_certificates(
        name=b'test', key=key, cert=cert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b'clave1234'),
    )
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    Path(destino).write_bytes(p12)
    return p12


RESP_RECIBIDA = {
    'estado': 'RECIBIDA', 'mensajes': [], 'numero_autorizacion': '', 'xml_autorizado': '',
}
RESP_AUTORIZADO = {
    'estado': 'AUTORIZADO', 'mensajes': [],
    'numero_autorizacion': '1507202601999999999999901001001000000001123456785',
    'xml_autorizado': '<factura id="comprobante"/>',
}


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class ClaveAccesoTests(TestCase):
    def test_modulo11_vector(self):
        # 48 dígitos calculados con el algoritmo (pesos 2..7 desde la derecha)
        cuerpo = '150720260199999999999990100100100000000112345678'
        self.assertEqual(digito_verificador_modulo11(cuerpo), '5')

    def test_clave_acceso_49_digitos(self):
        clave = generar_clave_acceso(
            fecha=date(2026, 7, 15), ruc='9999999999999', ambiente='1',
            serie='001001', secuencial=1, codigo_numerico='12345678',
        )
        self.assertEqual(len(clave), 49)
        self.assertTrue(validar_clave_acceso(clave))
        # Layout oficial de la ficha técnica:
        # fecha(8) tipo(2) ruc(13) ambiente(1) serie(6) secuencial(9)
        # código(8) tipo emisión(1) verificador(1)
        self.assertEqual(clave, '1507202601999999999999910010010000000011234567814')

    def test_clave_ambiente_y_tipo_emision(self):
        clave = generar_clave_acceso(
            fecha=date(2026, 7, 15), ruc='9999999999999', ambiente='2',
            serie='001001', secuencial=1, codigo_numerico='12345678',
        )
        # posición 24 = ambiente (1 pruebas / 2 producción)
        self.assertEqual(clave[23], '2')
        # posición 48 = tipo de emisión (1 normal / 2 contingencia)
        self.assertEqual(clave[47], '1')

    def test_validar_rechaza_claves_rotas(self):
        self.assertFalse(validar_clave_acceso('123'))
        self.assertFalse(validar_clave_acceso('1507202601999999999999901001001000000001123456780'))


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class XmlBuilderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vendedor', password='pass1234')
        cat = Category.objects.create(nombre='Hamburguesas')
        self.p1 = Product.objects.create(nombre='Doble', categoria=cat, precio=Decimal('3.50'))
        self.p2 = Product.objects.create(nombre='Papas', categoria=cat, precio=Decimal('2.00'))
        self.emisor = EmisorConfig.obtener()

    def _pedido(self):
        pedido = Order.objects.create(
            vendedor=self.user, cliente='Cliente Prueba',
            tipo_identificacion='05', identificacion='1710034065',
            direccion='Av. 123', email='c@test.com', descuento=Decimal('0.55'),
        )
        OrderItem.objects.create(pedido=pedido, producto=self.p1, cantidad=2, precio_unitario=self.p1.precio)
        OrderItem.objects.create(pedido=pedido, producto=self.p2, cantidad=1, precio_unitario=self.p2.precio)
        pedido.recalcular_totales()
        return pedido

    def test_estructura_y_totales_con_descuento(self):
        pedido = self._pedido()
        clave = generar_clave_acceso(
            fecha=date(2026, 7, 15), ruc=self.emisor.ruc, ambiente='1',
            serie='001001', secuencial=1, codigo_numerico='12345678',
        )
        xml = construir_xml(self.emisor, pedido, clave, 1, '001001000000001')
        doc = etree.fromstring(xml)

        self.assertEqual(doc.get('id'), 'comprobante')
        self.assertEqual(doc.find('infoTributaria/ruc').text, '9999999999999')
        self.assertEqual(doc.find('infoTributaria/claveAcceso').text, clave)
        self.assertEqual(doc.find('infoFactura/importeTotal').text, '8.45')
        self.assertEqual(doc.find('infoFactura/totalSinImpuestos').text, '7.35')
        self.assertEqual(doc.find('infoFactura/totalDescuento').text, '0.48')
        self.assertEqual(doc.find('infoFactura/razonSocialComprador').text, 'Cliente Prueba')
        self.assertEqual(doc.find('infoFactura/identificacionComprador').text, '1710034065')
        self.assertEqual(doc.find('infoFactura/tipoIdentificacionComprador').text, '05')
        impuesto = doc.find('infoFactura/totalConImpuestos/totalImpuesto')
        self.assertEqual(impuesto.find('baseImponible').text, '7.35')
        self.assertEqual(impuesto.find('valor').text, '1.10')
        self.assertEqual(impuesto.find('codigoPorcentaje').text, '4')
        self.assertEqual(doc.find('infoFactura/pagos/pago/formaPago').text, '01')

        detalles = doc.findall('detalles/detalle')
        self.assertEqual(len(detalles), 2)
        # Descuento (sin IVA) prorrateado: 2/3 y 1/3 (redondeo en la última)
        self.assertEqual(detalles[0].find('descuento').text, '0.37')
        self.assertEqual(detalles[1].find('descuento').text, '0.11')
        self.assertEqual(detalles[0].find('precioUnitario').text, '3.0435')
        self.assertEqual(detalles[1].find('precioUnitario').text, '1.7391')
        self.assertEqual(detalles[0].find('precioTotalSinImpuesto').text, '5.72')
        self.assertEqual(detalles[1].find('precioTotalSinImpuesto').text, '1.63')
        self.assertEqual(detalles[0].find('impuestos/impuesto/valor').text, '0.86')
        self.assertEqual(detalles[1].find('impuestos/impuesto/valor').text, '0.24')

    def _xml(self):
        pedido = self._pedido()
        clave = generar_clave_acceso(
            fecha=date(2026, 7, 15), ruc=self.emisor.ruc, ambiente='1',
            serie='001001', secuencial=1, codigo_numerico='12345678',
        )
        return etree.fromstring(
            construir_xml(self.emisor, pedido, clave, 1, '001001000000001')
        )

    def test_obligado_contabilidad_no_por_defecto(self):
        self.emisor.obligado_contabilidad = False
        doc = self._xml()
        self.assertEqual(doc.find('infoFactura/obligadoContabilidad').text, 'NO')

    def test_obligado_contabilidad_si_cuando_marcado(self):
        self.emisor.obligado_contabilidad = True
        doc = self._xml()
        self.assertEqual(doc.find('infoFactura/obligadoContabilidad').text, 'SI')

    def test_agente_retencion_omitido_por_defecto(self):
        self.emisor.agente_retencion = False
        doc = self._xml()
        self.assertIsNone(doc.find('infoTributaria/agenteRetencion'))

    def test_agente_retencion_emitido_cuando_marcado(self):
        self.emisor.agente_retencion = True
        doc = self._xml()
        self.assertEqual(doc.find('infoTributaria/agenteRetencion').text, '1')

    def test_contribuyente_especial_omitido_por_defecto(self):
        self.emisor.contribuyente_especial = ''
        doc = self._xml()
        self.assertIsNone(doc.find('infoFactura/contribuyenteEspecial'))

    def test_contribuyente_especial_emitido_antes_de_obligado(self):
        """Orden XSD: contribuyenteEspecial antes de obligadoContabilidad."""
        self.emisor.contribuyente_especial = '1234567890123'
        doc = self._xml()
        especial = doc.find('infoFactura/contribuyenteEspecial')
        self.assertEqual(especial.text, '1234567890123')
        self.assertEqual(especial.getnext().tag, 'obligadoContabilidad')

    def test_aritmetica_sri_por_linea(self):
        """Cada línea y el encabezado cumplen la validación de montos del SRI."""
        pedido = self._pedido()
        clave = generar_clave_acceso(
            fecha=date(2026, 7, 15), ruc=self.emisor.ruc, ambiente='1',
            serie='001001', secuencial=1, codigo_numerico='12345678',
        )
        doc = etree.fromstring(construir_xml(self.emisor, pedido, clave, 1, '001001000000001'))

        base_total = Decimal('0.00')
        desc_total = Decimal('0.00')
        for detalle in doc.findall('detalles/detalle'):
            cantidad = Decimal(detalle.find('cantidad').text)
            unitario = Decimal(detalle.find('precioUnitario').text)
            descuento = Decimal(detalle.find('descuento').text)
            base = Decimal(detalle.find('precioTotalSinImpuesto').text)
            self.assertLessEqual(
                abs(unitario * cantidad - descuento - base), Decimal('0.01')
            )
            base_total += base
            desc_total += descuento

        self.assertEqual(
            base_total, Decimal(doc.find('infoFactura/totalSinImpuestos').text)
        )
        self.assertEqual(
            desc_total, Decimal(doc.find('infoFactura/totalDescuento').text)
        )
        self.assertEqual(
            Decimal(doc.find('infoFactura/totalConImpuestos/totalImpuesto/baseImponible').text),
            base_total,
        )
        total = Decimal(doc.find('infoFactura/importeTotal').text)
        self.assertEqual(total, Decimal(doc.find('infoFactura/pagos/pago/total').text))

    def test_consumidor_final_por_defecto(self):
        pedido = Order.objects.create(vendedor=self.user)
        OrderItem.objects.create(pedido=pedido, producto=self.p1, cantidad=1, precio_unitario=self.p1.precio)
        pedido.recalcular_totales()
        xml = construir_xml(
            self.emisor, pedido,
            generar_clave_acceso(date(2026, 7, 15), '9999999999999', '1', '001001', 1, '12345678'),
            1, '001001000000001',
        )
        doc = etree.fromstring(xml)
        self.assertEqual(doc.find('infoFactura/razonSocialComprador').text, 'CONSUMIDOR FINAL')
        self.assertEqual(doc.find('infoFactura/identificacionComprador').text, '9999999999999')
        self.assertEqual(doc.find('infoFactura/tipoIdentificacionComprador').text, '07')

    def test_campo_adicional_vendedor(self):
        pedido = self._pedido()
        xml = construir_xml(
            self.emisor, pedido,
            generar_clave_acceso(date(2026, 7, 15), '9999999999999', '1', '001001', 1, '12345678'),
            1, '001001000000001',
        )
        doc = etree.fromstring(xml)
        campos = doc.findall('infoAdicional/campoAdicional')
        nombres = [c.get('nombre') for c in campos]
        self.assertIn('Vendedor', nombres)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class EmisionTests(TestCase):
    def setUp(self):
        p12_path = Path(MEDIA_TMP) / 'firmas' / 'firma_test.p12'
        _crear_p12(p12_path)

        self.emisor = EmisorConfig.obtener()
        self.emisor.ruc = '1710034065001'
        self.emisor.firma.name = 'firmas/firma_test.p12'
        self.emisor.clave_firma = 'clave1234'
        self.emisor.save()

        # Evita los sleep de reintento (2s/4s) en los tests de fallos de red
        self.patch_sleep = mock.patch('app.facturacion.sri.servicio_sri.time.sleep')
        self.patch_sleep.start()

        self.user = User.objects.create_user(username='vendedor', password='pass1234')
        cat = Category.objects.create(nombre='Bebidas')
        self.p = Product.objects.create(nombre='Cola', categoria=cat, precio=Decimal('1.00'))

    def tearDown(self):
        self.patch_sleep.stop()

    def _pedido_facturado(self):
        pedido = Order.objects.create(
            vendedor=self.user, cliente='Cliente X',
            tipo_identificacion='05', identificacion='1710034065',
        )
        OrderItem.objects.create(pedido=pedido, producto=self.p, cantidad=1, precio_unitario=self.p.precio)
        pedido.recalcular_totales()
        pedido.completar()
        return pedido

    def test_emite_firma_y_autoriza(self):
        pedido = self._pedido_facturado()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            comp = sri_emision.emitir_factura(pedido)

        self.assertEqual(comp.estado, Comprobante.ESTADO_AUTORIZADA)
        self.assertTrue(validar_clave_acceso(comp.clave_acceso))
        self.assertEqual(comp.numero_completo, '001001000000001')
        self.assertEqual(comp.numero, '001-001-000000001')

        doc = etree.fromstring(comp.xml_firmado.encode('utf-8'))
        sig = doc.find('{http://www.w3.org/2000/09/xmldsig#}Signature')
        self.assertIsNotNone(sig)
        self.assertTrue(comp.xml_autorizado)

        pedido.refresh_from_db()
        self.assertEqual(pedido.clave_acceso, comp.clave_acceso)
        self.assertEqual(pedido.secuencial_factura, '001001000000001')

    def test_secuencias_consecutivas_sin_duplicados(self):
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_RECIBIDA):
            comp1 = sri_emision.emitir_factura(self._pedido_facturado())
            comp2 = sri_emision.emitir_factura(self._pedido_facturado())

        self.assertEqual(comp1.secuencial, 1)
        self.assertEqual(comp2.secuencial, 2)
        self.assertNotEqual(comp1.clave_acceso, comp2.clave_acceso)
        self.assertEqual(
            Comprobante.objects.filter(numero_completo__in=[
                '001001000000001', '001001000000002',
            ]).count(), 2,
        )

    def test_idempotente(self):
        pedido = self._pedido_facturado()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            sri_emision.emitir_factura(pedido)
            comp2 = sri_emision.emitir_factura(pedido)

        self.assertEqual(Comprobante.objects.filter(pedido=pedido).count(), 1)
        self.assertEqual(comp2.estado, Comprobante.ESTADO_AUTORIZADA)

    def test_pendiente_se_reintenta(self):
        pedido = self._pedido_facturado()
        with mock.patch.object(
            sri_emision.servicio_sri, 'enviar', side_effect=ConnectionError('timeout')
        ):
            comp = sri_emision.emitir_factura(pedido)
        self.assertEqual(comp.estado, Comprobante.ESTADO_PENDIENTE)
        self.assertEqual(comp.intentos, 1)

        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_RECIBIDA):
            sri_emision.emitir_factura(pedido)
        comp.refresh_from_db()
        self.assertEqual(comp.estado, Comprobante.ESTADO_ENVIADA)
        self.assertEqual(comp.intentos, 2)

    def test_sin_firma_lanza_error(self):
        self.emisor.firma = None
        self.emisor.save()
        with self.assertRaises(sri_emision.FirmaNoConfigurada):
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_emisor_ruc_invalido_bloquea_emision(self):
        self.emisor.ruc = '9999999999999'
        self.emisor.save()
        with self.assertRaises(sri_emision.EmisorInvalido):
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_emisor_razon_social_vacia_bloquea_emision(self):
        self.emisor.razon_social = ''
        self.emisor.save()
        with self.assertRaises(sri_emision.EmisorInvalido):
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_emisor_direccion_vacia_bloquea_emision(self):
        self.emisor.direccion = ''
        self.emisor.save()
        with self.assertRaises(sri_emision.EmisorInvalido):
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_firma_de_otro_ruc_bloquea_emision(self):
        p12_path = Path(MEDIA_TMP) / 'firmas' / 'firma_otro_ruc.p12'
        _crear_p12(p12_path, ruc='0955480041001')
        self.emisor.firma.name = 'firmas/firma_otro_ruc.p12'
        self.emisor.save()
        with self.assertRaises(sri_emision.EmisorInvalido) as ctx:
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertIn('0955480041001', str(ctx.exception))
        self.assertIn('1710034065001', str(ctx.exception))
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_firma_sin_ruc_bloquea_emision(self):
        p12_path = Path(MEDIA_TMP) / 'firmas' / 'firma_sin_ruc.p12'
        _crear_p12(p12_path, ruc=None)
        self.emisor.firma.name = 'firmas/firma_sin_ruc.p12'
        self.emisor.save()
        with self.assertRaises(sri_emision.EmisorInvalido) as ctx:
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertIn('no contiene un RUC válido', str(ctx.exception))
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_firma_con_clave_incorrecta_bloquea_emision(self):
        self.emisor.clave_firma = 'clave-incorrecta'
        self.emisor.save()
        with self.assertRaises(sri_emision.EmisorInvalido) as ctx:
            sri_emision.emitir_factura(self._pedido_facturado())
        self.assertIn('contraseña', str(ctx.exception))
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_pedido_no_completado_lanza_error(self):
        pedido = self._pedido_facturado()
        pedido.estado = Order.ESTADO_PENDIENTE
        pedido.save()
        with self.assertRaises(sri_emision.PedidoInvalido):
            sri_emision.emitir_factura(pedido)

    def test_rechazada_guarda_mensajes(self):
        pedido = self._pedido_facturado()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value={
            'estado': 'DEVUELTA',
            'mensajes': ['41: Clave accesos incorrecta [ERROR]'],
            'numero_autorizacion': '', 'xml_autorizado': '',
        }):
            comp = sri_emision.emitir_factura(pedido)
        self.assertEqual(comp.estado, Comprobante.ESTADO_RECHAZADA)
        self.assertIn('41', comp.mensajes)

    def test_reenviar_pendientes(self):
        pedido = self._pedido_facturado()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            comp = sri_emision.emitir_factura(pedido)
            comp.estado = Comprobante.ESTADO_PENDIENTE
            comp.save()
            reintentados, _ = sri_emision.reenviar_pendientes(consultar=False)
        self.assertEqual(reintentados, 1)
        comp.refresh_from_db()
        self.assertEqual(comp.estado, Comprobante.ESTADO_AUTORIZADA)


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class FacturaViaCajaTests(TestCase):
    """Flujo completo: POS crea pedido pendiente, Caja cobra y emite la factura."""

    def setUp(self):
        p12_path = Path(MEDIA_TMP) / 'firmas' / 'firma_test.p12'
        _crear_p12(p12_path)
        emisor = EmisorConfig.obtener()
        emisor.ruc = '1710034065001'
        emisor.firma.name = 'firmas/firma_test.p12'
        emisor.clave_firma = 'clave1234'
        emisor.save()

        self.patch_sleep = mock.patch('app.facturacion.sri.servicio_sri.time.sleep')
        self.patch_sleep.start()

        self.user = User.objects.create_user(username='vendedor', password='pass1234')
        cat = Category.objects.create(nombre='Bebidas')
        self.p = Product.objects.create(nombre='Cola', categoria=cat, precio=Decimal('1.00'))
        self.client.login(username='vendedor', password='pass1234')

    def tearDown(self):
        self.patch_sleep.stop()

    def _crear_pedido_pos(self):
        """El POS crea un pedido pendiente (sin cobrar ni facturar)."""
        resp = self.client.post(
            reverse('orders:pos_crear'),
            data=json.dumps({'items': [{'producto_id': self.p.pk, 'cantidad': 2}]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        pedido = Order.objects.get(pk=resp.json()['pedido_id'])
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)
        self.assertEqual(Comprobante.objects.count(), 0)
        return pedido

    def _cobrar(self, pedido, follow=False, **extra):
        data = {
            'metodo_pago': 'efectivo',
            'recibido': '10.00',
            'tipo_identificacion': '05',
            'nombres': 'Cliente',
            'apellidos': 'Caja',
            'identificacion': '1710034065',
            'direccion': 'Av. Prueba',
            'email': 'cliente@test.com',
        }
        data.update(extra)
        return self.client.post(
            reverse('caja:caja_completar', args=[pedido.pk]), data=data, follow=follow,
        )

    def test_caja_cobra_y_emite_factura(self):
        pedido = self._crear_pedido_pos()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            resp = self._cobrar(pedido)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('caja:index'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.metodo_pago, Order.METODO_EFECTIVO)
        self.assertEqual(pedido.tipo_identificacion, '05')
        self.assertEqual(pedido.cliente, 'Cliente Caja')
        self.assertEqual(pedido.nombres, 'Cliente')
        self.assertEqual(pedido.apellidos, 'Caja')
        comp = pedido.comprobante
        self.assertEqual(comp.estado, Comprobante.ESTADO_AUTORIZADA)

    def test_caja_consumidor_final_autocompleta(self):
        pedido = self._crear_pedido_pos()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            resp = self._cobrar(
                pedido,
                tipo_identificacion='07',
                identificacion='', direccion='', email='',
            )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.tipo_identificacion, '07')
        self.assertEqual(pedido.cliente, 'CONSUMIDOR FINAL')
        self.assertEqual(pedido.identificacion, '9999999999999')
        self.assertEqual(pedido.comprobante.estado, Comprobante.ESTADO_AUTORIZADA)

    def test_caja_vuelto_en_efectivo(self):
        pedido = self._crear_pedido_pos()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            resp = self._cobrar(pedido, recibido='5.00', follow=True)
        self.assertContains(resp, 'Vuelto: $3.00')

    def test_caja_rechaza_ruc_corto(self):
        pedido = self._crear_pedido_pos()
        resp = self._cobrar(
            pedido, tipo_identificacion='04', razon_social='Empresa SA',
            identificacion='123456789012',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El RUC debe tener 13 dígitos')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)
        self.assertEqual(Comprobante.objects.count(), 0)

    def test_caja_rechaza_email_invalido(self):
        pedido = self._crear_pedido_pos()
        resp = self._cobrar(pedido, email='no-es-email')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El email es inválido')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_caja_rechaza_recibido_menor_al_total(self):
        pedido = self._crear_pedido_pos()  # total $2.00
        resp = self._cobrar(pedido, recibido='1.00')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'no cubre el total')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_falla_de_red_no_rompe_el_cobro(self):
        pedido = self._crear_pedido_pos()
        with mock.patch.object(
            sri_emision.servicio_sri, 'enviar', side_effect=ConnectionError('red caída')
        ):
            resp = self._cobrar(pedido)
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.comprobante.estado, Comprobante.ESTADO_PENDIENTE)

    def test_emisor_invalido_no_rompe_el_cobro(self):
        emisor = EmisorConfig.obtener()
        emisor.ruc = '9999999999999'
        emisor.save()
        pedido = self._crear_pedido_pos()
        resp = self._cobrar(pedido, follow=True)
        self.assertContains(resp, 'El RUC configurado no es válido')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertFalse(Comprobante.objects.exists())

    def test_cajera_procesa_pedido_de_otro_vendedor(self):
        """En Caja se procesan pedidos de cualquier vendedor (se busca por ticket)."""
        otro = User.objects.create_user(username='otro', password='pass1234')
        pedido = Order.objects.create(vendedor=otro)
        OrderItem.objects.create(pedido=pedido, producto=self.p, cantidad=1, precio_unitario=self.p.precio)
        pedido.recalcular_totales()
        with mock.patch.object(sri_emision.servicio_sri, 'enviar', return_value=RESP_RECIBIDA), \
             mock.patch.object(sri_emision.servicio_sri, 'consultar_autorizacion',
                               return_value=RESP_AUTORIZADO):
            resp = self._cobrar(pedido)
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.comprobante.estado, Comprobante.ESTADO_AUTORIZADA)


class ServicioSriTests(TestCase):
    """Parseo de respuestas zeep (objetos sin `.get`, con wrappers)."""

    class ZeepLike:
        """Simula un objeto CompoundValue de zeep: solo atributos."""

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def test_enviar_usa_parametro_xml(self):
        """El WSDL de Recepción define el parámetro como `xml`, no `comprobante`."""
        llamadas = {}
        respuesta = self.ZeepLike(
            RespuestaRecepcionComprobante=self.ZeepLike(estado='RECIBIDA')
        )

        class FakeService:
            def validarComprobante(self, **kwargs):
                llamadas.update(kwargs)
                return respuesta

        class FakeClient:
            def __init__(self):
                self.service = FakeService()

        with mock.patch.object(sri_servicio, '_cliente', return_value=FakeClient()):
            resultado = sri_servicio.enviar('<factura/>', '1')
        self.assertEqual(list(llamadas), ['xml'])
        self.assertIsInstance(llamadas['xml'], bytes)
        self.assertEqual(resultado['estado'], 'RECIBIDA')

    def test_estado_anidado_en_wrapper(self):
        resp = self.ZeepLike(
            RespuestaRecepcionComprobante=self.ZeepLike(estado='RECIBIDA')
        )
        self.assertEqual(sri_servicio._get(resp, 'estado'), 'RECIBIDA')

    def test_mensajes_recepcion(self):
        resp = self.ZeepLike(
            RespuestaRecepcionComprobante=self.ZeepLike(
                estado='DEVUELTA',
                comprobantes=self.ZeepLike(comprobante=[
                    self.ZeepLike(mensajes=self.ZeepLike(mensaje=[
                        self.ZeepLike(
                            identificador='43', mensaje='Clave inválida', tipo='ERROR',
                        ),
                    ])),
                ]),
            ),
        )
        self.assertEqual(
            sri_servicio._mensajes_de(resp),
            ['43: Clave inválida [ERROR]'],
        )

    def test_mensajes_autorizacion(self):
        resp = self.ZeepLike(
            RespuestaAutorizacionComprobante=self.ZeepLike(
                autorizaciones=self.ZeepLike(autorizacion=[
                    self.ZeepLike(mensajes=self.ZeepLike(mensaje=[
                        self.ZeepLike(
                            identificador='35', mensaje='Base imponible incorrecta', tipo='ERROR',
                        ),
                    ])),
                ]),
            ),
        )
        self.assertEqual(
            sri_servicio._mensajes_de(resp),
            ['35: Base imponible incorrecta [ERROR]'],
        )

    def test_consultar_autorizacion_autorizado(self):
        import base64
        import zlib
        xml_ok = b'<factura id="comprobante"/>'
        comp_b64 = base64.b64encode(
            zlib.compress(xml_ok, 9, -zlib.MAX_WBITS)
        ).decode('ascii')
        resp = self.ZeepLike(
            RespuestaAutorizacionComprobante=self.ZeepLike(
                autorizaciones=self.ZeepLike(autorizacion=[
                    self.ZeepLike(
                        estado='AUTORIZADO',
                        numeroAutorizacion='1234567890',
                        comprobante=comp_b64,
                    ),
                ]),
            ),
        )

        class FakeService:
            def autorizacionComprobante(self, **kwargs):
                self.kwargs = kwargs
                return resp

        class FakeClient:
            def __init__(self):
                self.service = FakeService()

        fake = FakeClient()
        with mock.patch.object(sri_servicio, '_cliente', return_value=fake):
            resultado = sri_servicio.consultar_autorizacion('123', '1')
        self.assertEqual(fake.service.kwargs, {'claveAccesoComprobante': '123'})
        self.assertEqual(resultado['estado'], 'AUTORIZADO')
        self.assertEqual(resultado['numero_autorizacion'], '1234567890')
        self.assertEqual(resultado['xml_autorizado'], xml_ok.decode('utf-8'))

    def test_consultar_autorizacion_no_autorizado(self):
        resp = self.ZeepLike(
            RespuestaAutorizacionComprobante=self.ZeepLike(
                autorizaciones=self.ZeepLike(autorizacion=[
                    self.ZeepLike(
                        estado='NO AUTORIZADO',
                        mensajes=self.ZeepLike(mensaje=[
                            self.ZeepLike(
                                identificador='34', mensaje='Documento no autorizado', tipo='ERROR',
                            ),
                        ]),
                    ),
                ]),
            ),
        )

        class FakeService:
            def autorizacionComprobante(self, **kwargs):
                return resp

        class FakeClient:
            def __init__(self):
                self.service = FakeService()

        with mock.patch.object(sri_servicio, '_cliente', return_value=FakeClient()):
            resultado = sri_servicio.consultar_autorizacion('123', '1')
        self.assertEqual(resultado['estado'], 'NO AUTORIZADO')
        self.assertIn('34: Documento no autorizado [ERROR]', resultado['mensajes'])


class PermisosFacturacionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass1234')
        self.admin.profile.rol = Profile.ROL_ADMIN
        self.admin.profile.save()
        self.emp = User.objects.create_user(username='emp', password='pass1234')

    def test_empleado_no_ve_listado(self):
        self.client.login(username='emp', password='pass1234')
        resp = self.client.get(reverse('facturacion:comprobante_list'))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('users:dashboard'))

    def test_admin_ve_listado(self):
        self.client.login(username='admin', password='pass1234')
        resp = self.client.get(reverse('facturacion:comprobante_list'))
        self.assertEqual(resp.status_code, 200)

    def test_anonimo_redirige_login(self):
        resp = self.client.get(reverse('facturacion:comprobante_list'))
        self.assertEqual(resp.status_code, 302)

    def test_config_crea_emisor_si_no_existe(self):
        self.client.login(username='admin', password='pass1234')
        resp = self.client.get(reverse('facturacion:config'))
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(EmisorConfig.obtener())


class PanelFacturacionTests(TestCase):
    """Páginas del panel dentro del proyecto (detalle, logs, secuencias, config)."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass1234')
        self.admin.profile.rol = Profile.ROL_ADMIN
        self.admin.profile.save()
        self.emp = User.objects.create_user(username='emp', password='pass1234')
        self.vendedor = User.objects.create_user(username='vendedor', password='pass1234')
        self.pedido = Order.objects.create(vendedor=self.vendedor, cliente='Consumidor final')
        self.comp = Comprobante.objects.create(
            pedido=self.pedido,
            clave_acceso='0808202601999999999999910010010000000018124196615',
            numero_completo='001001000000001',
            secuencial=1,
            xml_firmado='<factura id="comprobante"/>',
            mensajes='35: ARCHIVO NO CUMPLE ESTRUCTURA XML [ERROR] - RUC',
        )
        LogSri.objects.create(
            comprobante=self.comp, nivel=LogSri.NIVEL_ERROR,
            mensaje='Recepción devolvió el comprobante.',
        )

    def _login_admin(self):
        self.client.login(username='admin', password='pass1234')

    def test_paginas_admin_200(self):
        self._login_admin()
        for url in (
            reverse('facturacion:comprobante_list'),
            reverse('facturacion:comprobante_detail', args=[self.comp.pk]),
            reverse('facturacion:log_list'),
            reverse('facturacion:secuencia_list'),
            reverse('facturacion:config'),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_empleado_bloqueado(self):
        self.client.login(username='emp', password='pass1234')
        for url in (
            reverse('facturacion:comprobante_detail', args=[self.comp.pk]),
            reverse('facturacion:log_list'),
            reverse('facturacion:secuencia_list'),
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 302)
                self.assertRedirects(resp, reverse('users:dashboard'))

    def test_eliminar_rechazada(self):
        self._login_admin()
        self.comp.estado = Comprobante.ESTADO_RECHAZADA
        self.comp.save(update_fields=['estado'])
        self.pedido.clave_acceso = self.comp.clave_acceso
        self.pedido.secuencial_factura = self.comp.numero_completo
        self.pedido.save(update_fields=['clave_acceso', 'secuencial_factura'])
        resp = self.client.post(reverse('facturacion:comprobante_eliminar', args=[self.comp.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('facturacion:comprobante_list'))
        self.assertFalse(Comprobante.objects.filter(pk=self.comp.pk).exists())
        self.assertFalse(LogSri.objects.filter(comprobante=self.comp).exists())
        self.pedido.refresh_from_db()
        self.assertIsNone(self.pedido.clave_acceso)
        self.assertIsNone(self.pedido.secuencial_factura)

    def test_eliminar_autorizada_bloqueada(self):
        self._login_admin()
        self.comp.estado = Comprobante.ESTADO_AUTORIZADA
        self.comp.save(update_fields=['estado'])
        resp = self.client.post(reverse('facturacion:comprobante_eliminar', args=[self.comp.pk]))
        self.assertRedirects(resp, reverse('facturacion:comprobante_list'))
        self.assertTrue(Comprobante.objects.filter(pk=self.comp.pk).exists())

    def test_eliminar_requiere_post(self):
        self._login_admin()
        resp = self.client.get(reverse('facturacion:comprobante_eliminar', args=[self.comp.pk]))
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(Comprobante.objects.filter(pk=self.comp.pk).exists())

    def test_config_guarda_cambios(self):
        self._login_admin()
        emisor = EmisorConfig.obtener()
        resp = self.client.post(reverse('facturacion:config'), {
            'ruc': '1710034065001',
            'razon_social': emisor.razon_social,
            'nombre_comercial': emisor.nombre_comercial,
            'direccion': emisor.direccion,
            'telefono': '',
            'email': '',
            'ambiente': '1',
            'establecimiento': '001',
            'punto_emision': '001',
            'clave_firma': '',
        })
        self.assertEqual(resp.status_code, 302)
        emisor.refresh_from_db()
        self.assertEqual(emisor.ruc, '1710034065001')

    def test_config_rechaza_ruc_invalido(self):
        self._login_admin()
        resp = self.client.post(reverse('facturacion:config'), {
            'ruc': '123',
            'razon_social': 'X',
            'nombre_comercial': '',
            'direccion': 'X',
            'telefono': '',
            'email': '',
            'ambiente': '1',
            'establecimiento': '001',
            'punto_emision': '001',
            'clave_firma': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            'El RUC debe tener exactamente 13 dígitos.',
            resp.context['form'].errors['ruc'],
        )


@override_settings(MEDIA_ROOT=MEDIA_TMP)
class EmisorConfigFormTests(TestCase):
    """La firma se valida al guardar: clave correcta y RUC coincidente."""

    RUC_EMISOR = '1710034065001'

    def setUp(self):
        self.emisor = EmisorConfig.obtener()
        self.emisor.ruc = self.RUC_EMISOR
        self.emisor.firma = None
        self.emisor.clave_firma = ''
        self.emisor.save()

    def _p12_subido(self, nombre='firma_upload.p12', ruc='1710034065001'):
        datos = _crear_p12(Path(MEDIA_TMP) / 'firmas' / nombre, ruc=ruc)
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            nombre, datos, content_type='application/x-pkcs12',
        )

    def _datos(self, **extra):
        datos = {
            'ruc': self.RUC_EMISOR,
            'razon_social': 'EMPRESA TEST',
            'nombre_comercial': '',
            'direccion': 'Quito',
            'telefono': '',
            'email': '',
            'ambiente': '1',
            'establecimiento': '001',
            'punto_emision': '001',
            'clave_firma': 'clave1234',
        }
        datos.update(extra)
        return datos

    def test_firma_valida_con_ruc_coincidente(self):
        form = EmisorConfigForm(
            instance=self.emisor, data=self._datos(),
            files={'firma': self._p12_subido()},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_rechaza_clave_incorrecta(self):
        form = EmisorConfigForm(
            instance=self.emisor,
            data=self._datos(clave_firma='clave-mala'),
            files={'firma': self._p12_subido()},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'La clave no coincide con el archivo .p12 de la firma.',
            form.errors['clave_firma'],
        )

    def test_rechaza_ruc_distinto(self):
        form = EmisorConfigForm(
            instance=self.emisor,
            data=self._datos(),
            files={'firma': self._p12_subido(ruc='0955480041001')},
        )
        self.assertFalse(form.is_valid())
        mensaje = form.errors['firma'][0]
        self.assertIn('0955480041001', mensaje)
        self.assertIn(self.RUC_EMISOR, mensaje)

    def test_rechaza_firma_sin_ruc(self):
        form = EmisorConfigForm(
            instance=self.emisor,
            data=self._datos(),
            files={'firma': self._p12_subido(ruc=None)},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'no contiene un RUC válido',
            form.errors['firma'][0],
        )

    def test_exige_clave_si_hay_firma(self):
        form = EmisorConfigForm(
            instance=self.emisor,
            data=self._datos(clave_firma=''),
            files={'firma': self._p12_subido()},
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            'Cargá la clave del archivo .p12 para validar la firma.',
            form.errors['clave_firma'],
        )

    def test_valida_firma_existente_al_cambiar_otros_campos(self):
        p12_path = Path(MEDIA_TMP) / 'firmas' / 'firma_existente.p12'
        _crear_p12(p12_path)
        self.emisor.firma.name = 'firmas/firma_existente.p12'
        self.emisor.clave_firma = 'clave1234'
        self.emisor.save()
        form = EmisorConfigForm(
            instance=self.emisor,
            data=self._datos(razon_social='OTRO NOMBRE'),
        )
        self.assertTrue(form.is_valid(), form.errors)


class PdfFacturaTests(TestCase):
    """PDF A4 de la factura (generación y vista)."""

    def setUp(self):
        self.user = User.objects.create_user(username='vendedor', password='pass1234')
        cat = Category.objects.create(nombre='Bebidas')
        self.p = Product.objects.create(nombre='Cola', categoria=cat, precio=Decimal('1.00'))

    def _comp_autorizado(self):
        pedido = Order.objects.create(
            vendedor=self.user, cliente='Cliente X',
            tipo_identificacion='05', identificacion='1710034065',
        )
        OrderItem.objects.create(
            pedido=pedido, producto=self.p, cantidad=2,
            precio_unitario=self.p.precio,
        )
        pedido.recalcular_totales()
        pedido.completar()
        return Comprobante.objects.create(
            pedido=pedido,
            clave_acceso='1507202601999999999999910010010000000011234567815',
            numero_completo='001001000000001',
            secuencial=1,
            xml_firmado='<factura id="comprobante"/>',
            estado=Comprobante.ESTADO_AUTORIZADA,
            numero_autorizacion='1507202601999999999999901001001000000001123456785',
        )

    def test_genera_pdf_autorizado(self):
        from .sri.pdf import generar_pdf

        pdf = generar_pdf(self._comp_autorizado())
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertGreater(len(pdf), 1000)

    def test_vista_pdf_solo_admin(self):
        comp = self._comp_autorizado()
        admin = User.objects.create_user(username='admin', password='pass1234')
        admin.profile.rol = Profile.ROL_ADMIN
        admin.profile.save()
        self.client.login(username='admin', password='pass1234')
        resp = self.client.get(reverse('facturacion:comprobante_pdf', args=[comp.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))

    def test_vista_pdf_empleado_bloqueado(self):
        comp = self._comp_autorizado()
        User.objects.create_user(username='emp', password='pass1234')
        self.client.login(username='emp', password='pass1234')
        resp = self.client.get(reverse('facturacion:comprobante_pdf', args=[comp.pk]))
        self.assertEqual(resp.status_code, 302)
