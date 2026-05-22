from django.test import TestCase

from .models import Category, Product


class ProductTests(TestCase):
    def test_crear_producto(self):
        cat = Category.objects.create(nombre='Hamburguesas', orden=1)
        p = Product.objects.create(
            nombre='Cheeseburger', categoria=cat, precio=2500, costo=900
        )
        self.assertIn('Cheeseburger', str(p))
        self.assertEqual(p.margen, 1600)
