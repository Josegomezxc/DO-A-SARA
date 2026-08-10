from decimal import Decimal

from django.test import TestCase

from .forms import CategoryForm, ProductForm
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


class FormulariosTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(nombre='Bebidas')

    # ---------- Nombres ----------

    def test_nombre_con_letras_sueltas_se_normaliza(self):
        form = ProductForm(data={
            'nombre': 'c o      l a    s', 'categoria': self.cat.pk,
            'precio': '2.50', 'activo': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['nombre'], 'colas')

    def test_nombre_con_palabras_reales_se_conserva(self):
        form = CategoryForm(data={
            'nombre': 'Papas   Fritas', 'color': '#2563EB', 'activa': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['nombre'], 'Papas Fritas')

    def test_nombre_solo_espacios_rechazado(self):
        form = CategoryForm(data={'nombre': '     ', 'color': '#2563EB', 'activa': 'on'})
        self.assertFalse(form.is_valid())
        self.assertIn('El nombre es obligatorio.', form.errors['nombre'])

    def test_nombre_sin_normalizar_no_rompe_unico(self):
        """'Hamburguesas' y 'Hamburguesas ' deben colisionar tras normalizar."""
        Category.objects.create(nombre='Hamburguesas')
        form = CategoryForm(data={'nombre': 'Hamburguesas  ', 'activa': 'on'})
        self.assertFalse(form.is_valid())

    # ---------- Precio ----------

    def test_precio_mas_de_2_decimales_rechazado(self):
        form = ProductForm(data={
            'nombre': 'Cola', 'categoria': self.cat.pk,
            'precio': '1.005', 'activo': 'on',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('más de 2 decimales', form.errors['precio'][0])

    def test_precio_con_demasiados_enteros_rechazado(self):
        form = ProductForm(data={
            'nombre': 'Cola', 'categoria': self.cat.pk,
            'precio': '100000000', 'activo': 'on',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('8 dígitos enteros', form.errors['precio'][0])

    def test_precio_absurdo_con_coma_rechazado(self):
        form = ProductForm(data={
            'nombre': 'Cola', 'categoria': self.cat.pk,
            'precio': '111111111111111111,000000000000000111111111',
            'activo': 'on',
        })
        self.assertFalse(form.is_valid())

    def test_precio_valido_aceptado(self):
        form = ProductForm(data={
            'nombre': 'Cola', 'categoria': self.cat.pk,
            'precio': '99999999.99', 'activo': 'on',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['precio'], Decimal('99999999.99'))
