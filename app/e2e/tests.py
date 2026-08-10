"""Smoke tests e2e con Playwright sobre el servidor de pruebas de Django.

Los tests arrancan Chromium headless y navegan por los flujos reales:
login, POS (agregar/vaciar con popup), caja (cobro Consumidor Final con
la emisión SRI mockeada) y menú (crear + desactivar con popup).

La emisión real hacia el SRI (SOAP) se mockea: en la suite anterior colgaba
por la red. Se corre con:

    python manage.py test app.e2e.tests
"""
import os
import re
from decimal import Decimal
from unittest.mock import patch

# Playwright sync_api deja un event loop corriendo en el hilo principal, y
# Django interpreta eso como "contexto async" bloqueando las consultas a la BD
# (SynchronousOnlyOperation). Las queries se siguen ejecutando síncronas y sin
# riesgo: el loop solo corre durante las llamadas a Playwright.
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from playwright.sync_api import expect, sync_playwright

from app.orders.models import Order, OrderItem
from app.products.models import Category, Product
from app.users.models import Profile


class FakeComprobante:
    """Objeto mínimo que imita el comprobante devuelto por el SRI."""

    numero = '001-001-000000001'

    def get_estado_display(self):
        return 'Autorizada'


class BaseE2ETestCase(StaticLiveServerTestCase):
    """Arranca una ventana de Chromium por test y provee helpers.

    El navegador se abre/cierra en cada test (setUp/tearDown): nunca hay
    más de una ventana a la vez y cada test arranca limpio.

    Con PLAYWRIGHT_HEADED=1 la ventana es visible y cada paso va lento
    (slow_mo) para seguir el flujo; sin la variable corre headless.

    StaticLiveServerTestCase (y no LiveServerTestCase) para que el servidor
    de pruebas sirva los static de las apps: sin eso pos.js, main.js,
    validacion.js y jQuery dan 404 y los flujos JS no funcionan.
    """

    host = '127.0.0.1'

    def setUp(self):
        super().setUp()
        headed = os.environ.get('PLAYWRIGHT_HEADED') == '1'
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=not headed,
            slow_mo=450 if headed else 0,
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)

    def tearDown(self):
        self.context.close()
        self.browser.close()
        self._pw.stop()
        super().tearDown()

    def crear_usuario(self, username, password='clave123', es_admin=False):
        user = User.objects.create_user(username=username, password=password)
        # La señal post_save de User ya crea el Profile; solo actualizamos el rol.
        user.profile.rol = Profile.ROL_ADMIN if es_admin else Profile.ROL_EMPLEADO
        user.profile.save(update_fields=['rol'])
        return user

    def login(self, username, password='clave123'):
        self.page.goto(f'{self.live_server_url}{reverse("users:login")}')
        self.page.fill('#id_username', username)
        self.page.fill('#id_password', password)
        self.page.click('button[type="submit"]')
        self.page.wait_for_load_state('load')
        expect(self.page).to_have_url(re.compile(r'/cuentas/$'))


class LoginE2ETestCase(BaseE2ETestCase):
    def setUp(self):
        super().setUp()
        self.empleado = self.crear_usuario('empleado_login')
        self.admin = self.crear_usuario('admin_login', es_admin=True)

    def test_login_empleado_llega_al_dashboard(self):
        self.login('empleado_login')
        expect(self.page.locator('h1')).to_contain_text('Hola')

    def test_login_admin_llega_al_panel(self):
        self.login('admin_login')
        expect(self.page.locator('h1')).to_contain_text('Panel de administración')


class POSFlujoE2ETestCase(BaseE2ETestCase):
    def setUp(self):
        super().setUp()
        self.empleado = self.crear_usuario('empleado_pos')
        self.cat = Category.objects.create(nombre='Hamburguesas')
        self.producto = Product.objects.create(
            nombre='Hamburguesa Clásica',
            categoria=self.cat,
            precio=Decimal('8.50'),
        )

    def test_agregar_producto_y_vaciar_carrito_con_popup(self):
        self.login('empleado_pos')
        self.page.goto(f'{self.live_server_url}{reverse("orders:pos")}')

        self.page.select_option('#pos-categoria', str(self.cat.pk))
        expect(self.page.locator('#pos-producto-wrap')).to_be_visible()
        self.page.select_option('#pos-producto', str(self.producto.pk))
        expect(self.page.locator('#pos-btn-agregar')).to_be_visible()

        self.page.click('#pos-btn-agregar')
        expect(self.page.locator('#pos-cart-count')).to_have_text('1')
        expect(self.page.locator('#pos-total')).to_contain_text('8,5')

        # Cancelar NO vacía el carrito
        self.page.click('#pos-btn-vaciar')
        expect(self.page.locator('#confirmModal')).to_be_visible()
        self.page.click('#confirmModalCancelar')
        expect(self.page.locator('#confirmModal')).not_to_be_visible()
        expect(self.page.locator('#pos-cart-count')).to_have_text('1')

        # Confirmar SÍ vacía el carrito
        self.page.click('#pos-btn-vaciar')
        expect(self.page.locator('#confirmModal')).to_be_visible()
        self.page.click('#confirmModalBtn')
        expect(self.page.locator('#pos-cart-count')).to_have_text('0')
        expect(self.page.locator('#pos-cart-empty')).to_be_visible()


class CajaCobroE2ETestCase(BaseE2ETestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.crear_usuario('admin_caja', es_admin=True)
        self.cat = Category.objects.create(nombre='Bebidas')
        self.producto = Product.objects.create(
            nombre='Coca Cola', categoria=self.cat, precio=Decimal('1.50'),
        )
        self.pedido = Order.objects.create(
            vendedor=self.admin,
            subtotal=Decimal('1.50'),
            total=Decimal('1.50'),
            estado=Order.ESTADO_PENDIENTE,
        )
        OrderItem.objects.create(
            pedido=self.pedido,
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal('1.50'),
        )
        self.pedido.refresh_from_db()

    @patch('app.caja.views.emitir_factura', return_value=FakeComprobante())
    def test_cobro_consumidor_final_con_factura_mockeada(self, mock_emitir):
        self.login('admin_caja')

        # Buscar el pedido por número de ticket en caja
        self.page.goto(f'{self.live_server_url}{reverse("caja:index")}')
        self.page.fill('input[placeholder*="Buscar por número de ticket"]', self.pedido.numero)
        self.page.press('input[placeholder*="Buscar por número de ticket"]', 'Enter')
        # Con un solo resultado, el buscador redirige directo al detalle.
        expect(self.page).to_have_url(re.compile(r'/caja/\d+/$'))

        # Efectivo con vuelto
        self.page.select_option('#metodo_pago', Order.METODO_EFECTIVO)
        self.page.fill('#recibido', '5.00')
        expect(self.page.locator('#vuelto-box')).to_be_visible()
        expect(self.page.locator('#vuelto-amount')).to_contain_text('3,5')

        # Consumidor Final (07): se activa el switch y luego se elige 07
        # desde el select (el switch se apaga solo al elegir 07).
        self.page.click('label[for="switch-factura-datos"]')
        expect(self.page.locator('#receptor-fields')).to_be_visible()
        self.page.select_option('#tipo_identificacion', '07')
        expect(self.page.locator('#receptor-consumidor')).to_be_visible()
        expect(self.page.locator('#receptor-fields')).to_be_hidden()

        self.page.click('button:has-text("Cobrar y emitir factura")')
        expect(self.page).to_have_url(re.compile(r'/caja/$'))
        expect(self.page.locator('.alert-success')).to_contain_text('Cobrado')

        mock_emitir.assert_called_once()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(self.pedido.cliente, 'CONSUMIDOR FINAL')


class MenuGestionE2ETestCase(BaseE2ETestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.crear_usuario('admin_menu', es_admin=True)
        self.cat = Category.objects.create(nombre='Papas')

    def test_crear_y_desactivar_producto_con_popup(self):
        self.login('admin_menu')

        # Crear producto
        self.page.goto(f'{self.live_server_url}{reverse("products:product_create")}')
        self.page.fill('#id_nombre', 'Papas Fritas Grandes')
        self.page.select_option('#id_categoria', str(self.cat.pk))
        self.page.fill('#id_precio', '3.25')
        self.page.click('button:has-text("Guardar producto")')
        self.page.wait_for_load_state('load')
        expect(self.page).to_have_url(re.compile(r'/productos/$'))
        expect(self.page.locator('.product-table')).to_contain_text('Papas Fritas Grandes')

        # Desactivar desde el modal con el popup de confirmación
        row = self.page.locator('.product-row', has_text='Papas Fritas Grandes')
        row.click()
        expect(self.page.locator('#productModal')).to_be_visible()
        self.page.click('#modal-btn-desactivar')
        expect(self.page.locator('#confirmModal')).to_be_visible()
        self.page.click('#confirmModalBtn')
        self.page.wait_for_load_state('load')

        expect(self.page).to_have_url(re.compile(r'/productos/$'))
        producto = Product.objects.get(nombre='Papas Fritas Grandes')
        self.assertFalse(producto.activo)
        expect(
            self.page.locator('.product-row', has_text='Papas Fritas Grandes')
        ).to_contain_text('Inactivo')
