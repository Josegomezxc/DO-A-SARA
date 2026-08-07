from decimal import Decimal

from django.test import TestCase

from .models import Category, Product


class ProductTests(TestCase):
    def test_crear_producto(self):
        cat = Category.objects.create(nombre='Hamburguesas', orden=1)
        p = Product.objects.create(
            nombre='Cheeseburger', categoria=cat, precio=Decimal('2500.00')
        )
        self.assertIn('Cheeseburger', str(p))
        self.assertEqual(p.precio, Decimal('2500.00'))

    def test_slug_automatico_categoria(self):
        cat = Category.objects.create(nombre='Salchipapas Especiales')
        self.assertEqual(cat.slug, 'salchipapas-especiales')

    def test_desactivacion_logica_no_borra_historial(self):
        cat = Category.objects.create(nombre='Bebidas')
        p = Product.objects.create(nombre='Cola 500ml', categoria=cat, precio=Decimal('1.00'))
        p.activo = False
        p.save()
        self.assertFalse(Product.objects.get(pk=p.pk).activo)

    def test_orden_automatico_al_crear(self):
        c1 = Category.objects.create(nombre='Primera')
        c2 = Category.objects.create(nombre='Segunda')
        c3 = Category.objects.create(nombre='Tercera')
        self.assertEqual(c1.orden, 1)
        self.assertEqual(c2.orden, 2)
        self.assertEqual(c3.orden, 3)

    def test_orden_automatico_continua_despues_de_borrado(self):
        c1 = Category.objects.create(nombre='A')
        c2 = Category.objects.create(nombre='B')
        c1.delete()
        c3 = Category.objects.create(nombre='C')
        self.assertEqual(c3.orden, 3)

    def test_orden_explicito_se_respeta(self):
        c = Category.objects.create(nombre='Manual', orden=10)
        self.assertEqual(c.orden, 10)
        siguiente = Category.objects.create(nombre='Auto')
        self.assertEqual(siguiente.orden, 11)

    def test_slug_duplicado_no_rompe(self):
        c1 = Category.objects.create(nombre='Hamburguesas')
        c2 = Category.objects.create(nombre='hamburguesas')
        self.assertNotEqual(c1.slug, c2.slug)
        self.assertEqual(c1.slug, 'hamburguesas')
        self.assertEqual(c2.slug, 'hamburguesas-2')
        self.assertEqual(Category.objects.count(), 2)
