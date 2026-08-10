"""Crea las categorías del menú del puesto de papas y hamburguesas y,
opcionalmente, los productos del menú con sus precios.

Uso:
    python manage.py seed_menu                 # crea las categorías
    python manage.py seed_menu --con-productos # crea categorías + productos del menú
    python manage.py seed_menu --reset         # borra categorías/productos previos y carga todo

No toca usuarios, pedidos ni cajas existentes.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from app.orders.models import OrderItem
from app.products.models import Category, Product


# Las 9 categorías del menú, en el orden en que aparecen
CATEGORIAS = [
    {'nombre': 'Promociones',      'icono': 'fas fa-fire',          'color': '#e63946', 'orden': 1},
    {'nombre': 'Combos',           'icono': 'fas fa-hamburger',     'color': '#f4a261', 'orden': 2},
    {'nombre': 'Salchipapas',      'icono': 'fas fa-drumstick-bite','color': '#fb8500', 'orden': 3},
    {'nombre': 'Hamburguesas',     'icono': 'fas fa-hamburger',     'color': '#d62828', 'orden': 4},
    {'nombre': 'Perros Calientes', 'icono': 'fas fa-hotdog',        'color': '#e07a5f', 'orden': 5},
    {'nombre': 'Chuzos y Alitas',  'icono': 'fas fa-utensils',      'color': '#577590', 'orden': 6},
    {'nombre': 'Extras',           'icono': 'fas fa-plus-circle',   'color': '#8ecae6', 'orden': 7},
    {'nombre': 'Bebidas',          'icono': 'fas fa-glass-whiskey', 'color': '#219ebc', 'orden': 8},
    {'nombre': 'Postres',          'icono': 'fas fa-ice-cream',     'color': '#f9a8d4', 'orden': 9},
]


# (categoria, nombre, precio, descripcion)
PRODUCTOS = [
    # ----- Promociones -----
    ('Promociones', 'Promo Hamburguesa + Papas + Bebida', '5.50',
     'Incluye hamburguesa sencilla, porción de papas fritas y bebida personal de 300ml.'),
    ('Promociones', 'Promo Doble + Papas + Bebida', '6.50',
     'Incluye hamburguesa doble, porción de papas fritas y bebida personal de 300ml.'),
    ('Promociones', 'Promo 2 Salchipapas + 2 Bebidas', '7.00',
     'Incluye dos salchipapas sencillas y dos bebidas personales de 300ml.'),
    ('Promociones', 'Promo 2 Hamburguesas + Papas', '8.50',
     'Incluye dos hamburguesas sencillas y dos porciones de papas fritas.'),
    ('Promociones', 'Promo Familiar', '12.00',
     'Incluye 4 porciones de papas fritas y 4 bebidas de 500ml a elección.'),
    ('Promociones', 'Promo Pollo + Papas + Bebida', '6.00',
     'Incluye hamburguesa de pollo, porción de papas fritas y bebida personal de 300ml.'),

    # ----- Combos -----
    ('Combos', 'Combo Clásico', '5.00',
     'Hamburguesa sencilla, porción de papas fritas y cola de 300ml.'),
    ('Combos', 'Combo Doble', '6.00',
     'Hamburguesa doble, porción de papas fritas y cola de 300ml.'),
    ('Combos', 'Combo Pollo', '5.50',
     'Hamburguesa de pollo, porción de papas fritas y cola de 300ml.'),
    ('Combos', 'Combo Perro', '4.50',
     'Perro caliente especial, porción de papas fritas y cola de 300ml.'),
    ('Combos', 'Combo Salchipapa', '4.00',
     'Salchipapa especial, porción de papas fritas y cola de 300ml.'),
    ('Combos', 'Combo Familiar Hamburguesas', '12.00',
     'Cuatro hamburguesas sencillas y dos porciones de papas fritas.'),
    ('Combos', 'Combo Familiar Salchipapas', '10.00',
     'Cuatro salchipapas sencillas y cuatro colas de 300ml.'),
    ('Combos', 'Combo Alitas + Papas', '7.50',
     'Diez alitas BBQ o búfalo, porción de papas fritas y salsa a elección.'),
    ('Combos', 'Combo Chuzo + Papas', '5.00',
     'Chuzo de carne, porción de papas fritas y cola de 300ml.'),
    ('Combos', 'Combo Mexicano', '6.50',
     'Papas mexicanas, perro caliente especial y cola de 300ml.'),

    # ----- Salchipapas -----
    ('Salchipapas', 'Porción de papas fritas', '1.00',
     'Porción individual de papas fritas crujientes.'),
    ('Salchipapas', 'Papas con queso', '1.50',
     'Porción de papas fritas con queso derretido.'),
    ('Salchipapas', 'Papas con tocino', '1.75',
     'Porción de papas fritas con tocino crocante troceado.'),
    ('Salchipapas', 'Salchipapa sencilla', '1.50',
     'Papas fritas con salchicha, ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Salchipapa especial', '2.25',
     'Salchipapa sencilla con queso derretido y papa rellena.'),
    ('Salchipapas', 'Salchipapa mixta', '2.75',
     'Papas fritas con salchicha y carne de hamburguesa, ensalada y salsas.'),
    ('Salchipapas', 'Salchipapa con chorizo', '2.25',
     'Papas fritas con chorizo, ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Salchipapa con pollo', '2.75',
     'Papas fritas con pollo desmenuzado, ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Salchipapa con carne', '2.75',
     'Papas fritas con carne troceada, ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Salchipapa con chuzo', '3.00',
     'Papas fritas con chuzo de carne desarmado, ensalada y salsas.'),
    ('Salchipapas', 'Papi pollo', '2.50',
     'Papas fritas con pollo crujiente, ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Papi carne', '2.50',
     'Papas fritas con carne de hamburguesa, ensalada, mayonesa y salsa de tomate.'),
    ('Salchipapas', 'Papi pollo XXL', '4.50',
     'Porción grande de papas con pollo crujiente, ensalada y salsas.'),
    ('Salchipapas', 'Papi carne XXL', '4.50',
     'Porción grande de papas con carne, ensalada y salsas.'),
    ('Salchipapas', 'Papi mixto XXL', '5.00',
     'Porción grande de papas con pollo y carne, ensalada y salsas.'),
    ('Salchipapas', 'Papas manchadas', '2.50',
     'Papas fritas con queso cheddar y tocino crocante.'),
    ('Salchipapas', 'Papas supremas', '4.00',
     'Papas fritas con queso cheddar, tocino y salchicha troceada.'),
    ('Salchipapas', 'Papas cargadas', '5.50',
     'Papas fritas con carne, pollo, queso cheddar y tocino.'),
    ('Salchipapas', 'Papas mexicanas', '4.00',
     'Papas fritas con carne molida, pimiento, maíz, queso y salsas.'),
    ('Salchipapas', 'Papas con huevo', '2.00',
     'Porción de papas fritas con huevo frito, ensalada y salsas.'),
    ('Salchipapas', 'Papas con chuzo picante', '3.25',
     'Porción grande de papas con chuzo de carne picante, ensalada y salsas.'),
    ('Salchipapas', 'Papa rellena', '1.50',
     'Papa rellena de carne con ensalada, mayonesa, queso y bebida de 300ml a elección.'),
    ('Salchipapas', 'Salchipapa loca', '3.75',
     'Salchipapa sencilla con chuzo de pollo y carne troceada.'),
    ('Salchipapas', 'Salchipapa ranchera', '3.50',
     'Papas fritas con chorizo, tocino, queso derretido y salsas.'),
    ('Salchipapas', 'Papas de la casa', '4.25',
     'Papas fritas con salchicha, chorizo y pollo, queso cheddar y salsas.'),

    # ----- Hamburguesas -----
    ('Hamburguesas', 'Hamburguesa sencilla', '2.50',
     'Carne de res, lechuga, tomate, cebolla, salsa de tomate y mayonesa.'),
    ('Hamburguesas', 'Hamburguesa con queso', '3.00',
     'Hamburguesa sencilla con queso derretido.'),
    ('Hamburguesas', 'Hamburguesa con tocino', '3.50',
     'Hamburguesa sencilla con tocino crocante.'),
    ('Hamburguesas', 'Hamburguesa doble', '4.25',
     'Doble carne, queso, lechuga, tomate, cebolla y salsas.'),
    ('Hamburguesas', 'Hamburguesa especial', '4.50',
     'Carne, queso, tocino, huevo frito, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa ranchera', '4.50',
     'Carne, chorizo, frijoles, queso, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa de pollo', '3.25',
     'Pollo, lechuga, tomate, cebolla, mayonesa y salsa de tomate.'),
    ('Hamburguesas', 'Hamburguesa crispy', '3.75',
     'Pollo crujiente, queso, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa BBQ', '3.75',
     'Carne, queso, cebolla caramelizada, tocino y salsa BBQ.'),
    ('Hamburguesas', 'Hamburguesa doble tocino', '5.25',
     'Doble carne, doble tocino, queso, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa doble queso', '4.75',
     'Doble carne, doble queso, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa hawaiana', '4.00',
     'Carne, piña, queso, jamón, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa mexicana', '4.25',
     'Carne, guacamole, jalapeños, queso, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa vegetariana', '3.75',
     'Medallón de garbanzos, lechuga, tomate, cebolla caramelizada y salsas.'),
    ('Hamburguesas', 'Hamburguesa de salchicha', '3.00',
     'Salchicha, queso, lechuga, tomate, cebolla y salsas.'),
    ('Hamburguesas', 'Hamburguesa XL', '6.50',
     'Doble carne, doble queso, tocino, huevo, cebolla caramelizada y salsas.'),
    ('Hamburguesas', 'Hamburguesa con papas', '3.50',
     'Hamburguesa sencilla acompañada de porción de papas fritas.'),
    ('Hamburguesas', 'Hamburguesa doble con papas', '5.25',
     'Hamburguesa doble acompañada de porción de papas fritas.'),
    ('Hamburguesas', 'Hamburguesa de pollo con papas', '4.25',
     'Hamburguesa de pollo acompañada de porción de papas fritas.'),
    ('Hamburguesas', 'Hamburguesa suprema', '5.75',
     'Doble carne, queso, tocino, jamón, huevo, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa americana', '5.00',
     'Carne, queso cheddar, tocino, huevo frito, lechuga, tomate y salsas.'),
    ('Hamburguesas', 'Hamburguesa de la casa', '4.75',
     'Doble carne, queso derretido, cebolla caramelizada, lechuga, tomate y salsas.'),

    # ----- Perros Calientes -----
    ('Perros Calientes', 'Perro sencillo', '1.50',
     'Salchicha, pan, papa chips, ensalada, mayonesa, mostaza y salsa de tomate.'),
    ('Perros Calientes', 'Perro especial', '2.50',
     'Perro sencillo con huevo, queso derretido y cebolla caramelizada.'),
    ('Perros Calientes', 'Perro doble', '3.00',
     'Doble salchicha, papa chips, ensalada, mayonesa, mostaza y salsa de tomate.'),
    ('Perros Calientes', 'Perro con tocino', '3.00',
     'Perro sencillo con tocino crocante y queso derretido.'),
    ('Perros Calientes', 'Perro americano', '3.25',
     'Perro sencillo con tocino, queso cheddar y huevo frito.'),
    ('Perros Calientes', 'Perro de pollo', '2.75',
     'Salchicha de pollo, papa chips, ensalada, mayonesa, mostaza y salsa de tomate.'),
    ('Perros Calientes', 'Perro supremo', '4.00',
     'Doble salchicha, tocino, queso derretido, huevo, papa chips y salsas.'),
    ('Perros Calientes', 'Perro con papas', '2.50',
     'Perro sencillo acompañado de porción de papas fritas.'),

    # ----- Chuzos y Alitas -----
    ('Chuzos y Alitas', 'Chuzo de pollo', '2.00',
     'Pincho de pollo a la parrilla con papas fritas y salsas.'),
    ('Chuzos y Alitas', 'Chuzo de carne', '2.50',
     'Pincho de carne a la parrilla con papas fritas y salsas.'),
    ('Chuzos y Alitas', 'Chuzo mixto', '2.75',
     'Pincho de pollo y carne a la parrilla con papas fritas y salsas.'),
    ('Chuzos y Alitas', 'Chuzo con salchipapa', '4.00',
     'Chuzo de carne con porción de salchipapa sencilla.'),
    ('Chuzos y Alitas', 'Chuzo supremo', '3.50',
     'Chuzo grande de carne y pollo con papa rellena y salsas.'),
    ('Chuzos y Alitas', 'Alitas 6 unidades', '4.00',
     'Seis alitas de pollo con salsa BBQ o búfalo y papas fritas.'),
    ('Chuzos y Alitas', 'Alitas 10 unidades', '5.50',
     'Diez alitas de pollo con salsa BBQ o búfalo y papas fritas.'),
    ('Chuzos y Alitas', 'Alitas 12 unidades', '6.50',
     'Doce alitas de pollo con salsa BBQ o búfalo y papas fritas.'),

    # ----- Extras -----
    ('Extras', 'Extra queso', '0.50', 'Porción de queso derretido.'),
    ('Extras', 'Extra tocino', '0.75', 'Porción de tocino crocante.'),
    ('Extras', 'Extra carne', '1.00', 'Porción extra de carne de hamburguesa.'),
    ('Extras', 'Extra pollo', '1.00', 'Porción extra de pollo.'),
    ('Extras', 'Extra salchicha', '0.75', 'Porción extra de salchicha.'),
    ('Extras', 'Extra huevo', '0.50', 'Huevo frito adicional.'),
    ('Extras', 'Extra ensalada', '0.25', 'Porción de ensalada.'),
    ('Extras', 'Extra mayonesa', '0.25', 'Porción de mayonesa.'),
    ('Extras', 'Extra salsa de tomate', '0.25', 'Porción de salsa de tomate.'),
    ('Extras', 'Extra mostaza', '0.25', 'Porción de mostaza.'),
    ('Extras', 'Salsa BBQ', '0.50', 'Porción de salsa BBQ.'),
    ('Extras', 'Salsa de ají', '0.25', 'Porción de salsa de ají.'),

    # ----- Bebidas -----
    ('Bebidas', 'Cola de 300ml', '0.60', 'Bebida gaseosa personal a elección.'),
    ('Bebidas', 'Cola de 500ml', '1.00', 'Bebida gaseosa a elección.'),
    ('Bebidas', 'Cola de 1 Litro', '1.50', 'Bebida gaseosa familiar a elección.'),
    ('Bebidas', 'Cola de 1.35 Litros', '2.00', 'Bebida gaseosa familiar a elección.'),
    ('Bebidas', 'Agua sin gas 500ml', '0.75', 'Agua purificada en botella.'),
    ('Bebidas', 'Agua con gas 500ml', '0.90', 'Agua mineral con gas.'),
    ('Bebidas', 'Jugo natural de naranja', '1.25', 'Jugo de naranja recién exprimido de 400ml.'),
    ('Bebidas', 'Jugo natural de mora', '1.25', 'Jugo de mora batido en agua de 400ml.'),
    ('Bebidas', 'Jugo natural de guanábana', '1.25', 'Jugo de guanábana batido en leche de 400ml.'),
    ('Bebidas', 'Limonada', '1.00', 'Limonada natural de 400ml.'),
    ('Bebidas', 'Batido de banano', '1.75', 'Batido de banano con leche de 400ml.'),
    ('Bebidas', 'Batido de chocolate', '1.75', 'Batido de chocolate con leche de 400ml.'),
    ('Bebidas', 'Café', '1.00', 'Café de la casa de 200ml.'),
    ('Bebidas', 'Café con leche', '1.25', 'Café con leche de 250ml.'),

    # ----- Postres -----
    ('Postres', 'Helado de bola', '1.00', 'Helado artesanal de bola a elección.'),
    ('Postres', 'Helado de vaso', '1.50', 'Helado de vaso con cobertura a elección.'),
    ('Postres', 'Flan de la casa', '1.50', 'Flan casero con caramelo.'),
    ('Postres', 'Brownie con helado', '2.50', 'Brownie de chocolate con bola de helado.'),
    ('Postres', 'Pie de limón', '1.75', 'Porción de pie de limón.'),
    ('Postres', 'Fresas con crema', '2.00', 'Fresas frescas con crema batida.'),
]


class Command(BaseCommand):
    help = 'Carga las 9 categorías y los productos del menú del puesto de papas y hamburguesas.'

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
            # Los productos referenciados por pedidos no se pueden borrar
            # (on_delete=PROTECT): se desactivan para no romper tickets históricos.
            referenciados = list(
                OrderItem.objects.values_list('producto_id', flat=True).distinct()
            )
            Product.objects.exclude(pk__in=referenciados).delete()
            n_conservados = Product.objects.filter(pk__in=referenciados).update(activo=False)
            if n_conservados:
                self.stdout.write(self.style.WARNING(
                    f'  {n_conservados} producto(s) en pedidos conservados e inactivados.'
                ))
            Category.objects.filter(productos__isnull=True).delete()

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
