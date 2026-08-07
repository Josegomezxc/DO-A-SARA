from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.products.models import Category, Product

from .models import Order, OrderItem


class OrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='vendedor', password='pass1234')
        cat = Category.objects.create(nombre='Hamburguesas')
        self.p1 = Product.objects.create(nombre='Doble', categoria=cat, precio=3000)
        self.p2 = Product.objects.create(nombre='Simple', categoria=cat, precio=2000)

    def test_pedido_recalcula_total(self):
        pedido = Order.objects.create(vendedor=self.user)
        OrderItem.objects.create(pedido=pedido, producto=self.p1, cantidad=2, precio_unitario=3000)
        OrderItem.objects.create(pedido=pedido, producto=self.p2, cantidad=1, precio_unitario=2000)
        pedido.recalcular_totales()
        self.assertEqual(pedido.subtotal, Decimal('8000.00'))
        self.assertEqual(pedido.total, Decimal('8000.00'))

    def test_numero_se_genera(self):
        pedido = Order.objects.create(vendedor=self.user)
        self.assertTrue(pedido.numero.startswith('P-'))

    def test_recalcular_rellena_desglose_iva(self):
        pedido = Order.objects.create(vendedor=self.user)
        OrderItem.objects.create(pedido=pedido, producto=self.p1, cantidad=1, precio_unitario=3000)
        pedido.recalcular_totales()
        self.assertEqual(pedido.subtotal_iva, Decimal('3000.00'))
        self.assertEqual(pedido.subtotal_cero, Decimal('0.00'))
        self.assertEqual(pedido.valor_iva, Decimal('450.00'))
        self.assertEqual(pedido.iva_subtotal, Decimal('450.00'))
        self.assertEqual(pedido.subtotal_sin_iva, Decimal('2550.00'))


class PermisosPedidosTests(TestCase):
    def setUp(self):
        from app.users.models import Profile

        self.admin = User.objects.create_user(username='admin', password='pass1234')
        self.admin.profile.rol = Profile.ROL_ADMIN
        self.admin.profile.save()

        self.emp1 = User.objects.create_user(username='emp1', password='pass1234')
        self.emp2 = User.objects.create_user(username='emp2', password='pass1234')
        cat = Category.objects.create(nombre='Bebidas')
        self.p = Product.objects.create(nombre='Cola', categoria=cat, precio=1000)
        self.pedido_emp2 = Order.objects.create(vendedor=self.emp2)

    def test_empleado_no_ve_pedido_ajeno(self):
        self.client.login(username='emp1', password='pass1234')
        resp = self.client.get(reverse('orders:order_detail', args=[self.pedido_emp2.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_empleado_no_completa_pedido_ajeno(self):
        self.client.login(username='emp1', password='pass1234')
        resp = self.client.post(reverse('orders:order_completar', args=[self.pedido_emp2.pk]))
        self.assertEqual(resp.status_code, 404)
        self.pedido_emp2.refresh_from_db()
        self.assertEqual(self.pedido_emp2.estado, Order.ESTADO_PENDIENTE)

    def test_ticket_requiere_login(self):
        resp = self.client.get(reverse('orders:order_ticket', args=[self.pedido_emp2.pk]))
        self.assertIn(resp.status_code, (302, 403))

    def test_empleado_no_ve_ticket_ajeno(self):
        self.client.login(username='emp1', password='pass1234')
        resp = self.client.get(reverse('orders:order_ticket', args=[self.pedido_emp2.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_admin_ve_pedido_de_empleado(self):
        self.client.login(username='admin', password='pass1234')
        resp = self.client.get(reverse('orders:order_detail', args=[self.pedido_emp2.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_no_se_cancela_pedido_completado(self):
        self.pedido_emp2.completar(usuario=self.emp2)
        self.client.login(username='emp2', password='pass1234')
        resp = self.client.post(reverse('orders:order_cancelar', args=[self.pedido_emp2.pk]))
        self.pedido_emp2.refresh_from_db()
        self.assertEqual(self.pedido_emp2.estado, Order.ESTADO_COMPLETADO)

    def test_no_se_edita_pedido_completado(self):
        self.pedido_emp2.completar(usuario=self.emp2)
        self.client.login(username='emp2', password='pass1234')
        resp = self.client.post(
            reverse('orders:order_update', args=[self.pedido_emp2.pk]),
            {'cliente': 'Cliente X', 'metodo_pago': 'efectivo', 'descuento': '0', 'notas': ''},
        )
        self.pedido_emp2.refresh_from_db()
        self.assertEqual(self.pedido_emp2.cliente, '')


class POSAPITests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user(username='cajero', password='pass1234')
        cat = Category.objects.create(nombre='Papas')
        self.p = Product.objects.create(nombre='Porción', categoria=cat, precio=Decimal('2.50'))

    def _crear_pedido(self, payload):
        return self.client.post(
            reverse('orders:pos_crear'),
            data=payload,
            content_type='application/json',
        )

    def test_crear_pedido_ok(self):
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 2}],
            'completar': True,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['total'], '5.00')

    def test_completar_string_false_no_crea_completado(self):
        """'false' como string NO debe interpretarse como verdadero."""
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 1}],
            'completar': 'false',
        })
        self.assertTrue(resp.json()['ok'])
        pedido = Order.objects.get(pk=resp.json()['pedido_id'])
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_descuento_mayor_al_subtotal_rechazado(self):
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 1}],
            'descuento': '99.00',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])
        self.assertEqual(Order.objects.count(), 0)

    def test_pos_requiere_login(self):
        resp = self._crear_pedido({'items': [{'producto_id': self.p.pk, 'cantidad': 1}]})
        self.assertEqual(resp.status_code, 302)
