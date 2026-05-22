"""Crea las 6 categorías del menú real de Doña Sara y, opcionalmente,
los productos del menú con sus precios.

Uso:
    python manage.py seed_menu                 # crea las categorías
    python manage.py seed_menu --con-productos # crea categorías + productos del menú
    python manage.py seed_menu --reset         # borra categorías/productos previos y carga todo

No toca usuarios, pedidos ni cajas existentes.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from app.products.models import Category, Product


# Las 6 categorías del menú real, en el orden en que aparecen
CATEGORIAS = [
    {'nombre': 'Promociones',  'icono': 'fas fa-fire',         'color': '#e63946', 'orden': 1},
    {'nombre': 'Combos',       'icono': 'fas fa-hamburger',    'color': '#f4a261', 'orden': 2},
    {'nombre': 'Salchipapas',  'icono': 'fas fa-drumstick-bite','color': '#fb8500', 'orden': 3},
    {'nombre': 'Hamburguesas', 'icono': 'fas fa-hamburger',    'color': '#d62828', 'orden': 4},
    {'nombre': 'Extras',       'icono': 'fas fa-plus-circle',  'color': '#8ecae6', 'orden': 5},
    {'nombre': 'Bebidas',      'icono': 'fas fa-glass-whiskey','color': '#219ebc', 'orden': 6},
]


# (categoria, nombre, precio, descripcion)
PRODUCTOS = [
    # ----- Promociones -----
    ('Promociones', 'Promo XXL Papi Pollo', '10.00',
     'Incluye una papi pollo XXL con pechuga y una papi pollo XXL con pierna con elección de ensalada, mayonesa, salsa de tomate y una coca cola de 1 Lt.'),

    # ----- Combos -----
    ('Combos', 'Combo Mix', '6.00',
     'Incluye hamburguesa Benito, papas manchadas y coca cola 500ml.'),
    ('Combos', 'Combo Especial', '12.00',
     'Incluye una hamburguesa Crispy del Pana Benito y una hamburguesa Gran Benito, acompañado de una coca cola de 1 Lt.'),

    # ----- Salchipapas -----
    ('Salchipapas', 'Porción de papas fritas', '1.00',
     'Porción individual de papas fritas crujientes.'),
    ('Salchipapas', 'Bolita del Sabor', '1.50',
     'Incluye deliciosa papa rellena de carne, ensalada, mayonesa, queso rallado y bebida personal a elección de 300ml.'),
    ('Salchipapas', 'Papas con Chorizo', '1.25',
     'Incluye a elección ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Papas con Chuzo Picante', '1.25',
     'Incluye a elección ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Papas con Chorizo Mandingo', '2.25',
     'Incluye a elección ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Papi Pollo', '2.50',
     'Incluye a elección ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Las Manchadas del Pana Benito', '2.00',
     'Contiene papas fritas, queso cheddar y tocino.'),
    ('Salchipapas', 'Papa Suprema Manchada del Pana Benito', '6.00',
     'Incluye 10 nuggets de pollo, tocino troceado, cheddar y papas fritas.'),
    ('Salchipapas', 'Papas La Explosión del Pana Benito', '5.00',
     'Incluye dos porciones de carne de hamburguesa troceada en cuadritos, gran porción de papas fritas y queso cheddar.'),
    ('Salchipapas', 'Papi Pollo XXL con Pechuga', '5.00',
     'Incluye a elección ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Papi Pollo XXL con Pierna', '4.00',
     'Incluye a elección ensalada, mayonesa y salsa de tomate.'),

    # ----- Hamburguesas -----
    ('Hamburguesas', 'Hamburguesa Pana Benito', '2.50',
     'Incluye carne, queso cheddar laminado, lechuga, tomate, cebolla caramelizada, salsa de tomate, mayonesa, mostaza y papas fritas.'),
    ('Hamburguesas', 'Hamburguesa Benito', '3.75',
     'Incluye carne, tocino, lechuga, tomate, cebolla caramelizada, queso cheddar laminado, huevo, salsa de tomate, mayonesa, mostaza y porción de papas fritas.'),
    ('Hamburguesas', 'Hamburguesa Gran Benito', '7.00',
     'Incluye doble carne, queso cheddar laminado, huevo frito, tocino, lechuga, tomate, cebolla caramelizada, mayonesa, mostaza, salsa de tomate, papas fritas.'),
    ('Hamburguesas', 'Hamburguesa La Crispy del Pana Benito', '6.00',
     'Incluye pollo, tocino, cebolla caramelizada, queso cheddar laminado, lechuga, tomate, salsa de tomate, mostaza, mayonesa y porción de papas fritas.'),

    # ----- Extras -----
    ('Extras', 'Extra Ensalada', '0.25', 'Porción de ensalada.'),
    ('Extras', 'Extra Mayonesa', '0.25', 'Porción de mayonesa.'),
    ('Extras', 'Extra Salsa de Tomate', '0.25', 'Porción de salsa de tomate.'),

    # ----- Bebidas -----
    ('Bebidas', 'Cola Fanta de 300ml',     '0.60', ''),
    ('Bebidas', 'Cola Sprite de 300ml',    '0.60', ''),
    ('Bebidas', 'Cola Fioravanti de 300ml','0.60', ''),
    ('Bebidas', 'Inka Cola de 300ml',      '0.60', ''),
    ('Bebidas', 'Coca Cola de 300ml',      '0.75', ''),
    ('Bebidas', 'Squiz de Naranja de 1 Litro', '0.80', ''),
    ('Bebidas', 'Coca Cola de 500ml',      '1.00', ''),
    ('Bebidas', 'Coca Cola de 1 Litro',    '1.50', ''),
    ('Bebidas', 'Coca Cola de 1.35 Litros','2.00', ''),
]


class Command(BaseCommand):
    help = 'Carga las 6 categorías y los productos del menú de Doña Sara.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--con-productos', action='store_true',
            help='Además de las categorías, crea los productos del menú.',
        )
        parser.add_argument(
            '--reset', action='store_true',
            help='Borra categorías y productos previos antes de crear (NO toca pedidos ni cajas).',
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts['reset']:
            self.stdout.write(self.style.WARNING(
                'Eliminando categorías y productos previos...'
            ))
            Product.objects.all().delete()
            Category.objects.all().delete()

        # ------ Categorías ------
        cats = {}
        for c in CATEGORIAS:
            cat, created = Category.objects.update_or_create(
                nombre=c['nombre'],
                defaults={
                    'icono': c['icono'],
                    'color': c['color'],
                    'orden': c['orden'],
                    'activa': True,
                },
            )
            cats[c['nombre']] = cat
            estado = 'creada' if created else 'actualizada'
            self.stdout.write(f'  Categoría "{c["nombre"]}" {estado}.')
        self.stdout.write(self.style.SUCCESS(f'{len(cats)} categorías listas.'))

        # ------ Productos (opcional) ------
        if opts['con_productos']:
            creados = 0
            actualizados = 0
            for cat_nombre, nombre, precio, desc in PRODUCTOS:
                cat = cats.get(cat_nombre)
                if not cat:
                    self.stdout.write(self.style.ERROR(
                        f'  Categoría "{cat_nombre}" no encontrada, salteo "{nombre}".'
                    ))
                    continue
                prod, created = Product.objects.update_or_create(
                    nombre=nombre,
                    defaults={
                        'categoria': cat,
                        'precio': Decimal(precio),
                        'descripcion': desc,
                        'activo': True,
                    },
                )
                if created:
                    creados += 1
                else:
                    actualizados += 1
            self.stdout.write(self.style.SUCCESS(
                f'{creados} productos creados, {actualizados} actualizados.'
            ))

        self.stdout.write(self.style.SUCCESS('\nMenú cargado correctamente.'))
