from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from app.products.models import Category, Product

from .models import CashRegister, Order, OrderItem


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

    def test_caja_diferencia(self):
        caja = CashRegister.objects.create(
            abierta_por=self.user, monto_inicial=Decimal('1000')
        )
        caja.monto_final_real = Decimal('1500')
        caja.save()
        self.assertEqual(caja.diferencia, Decimal('500.00'))
