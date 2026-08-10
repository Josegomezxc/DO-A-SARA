from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.products.models import Category, Product

from .models import Order, OrderItem
from .validators import (
    errores_monto, errores_nombre, es_cedula_valida, es_pasaporte_valido,
    es_ruc_valido, normalizar_nombre, validar_identificacion,
)


class ValidadoresIdentificacionTests(TestCase):
    """Algoritmos SRI: cédula (módulo 10), RUC (módulo 11), pasaporte."""

    def test_cedula_valida(self):
        self.assertTrue(es_cedula_valida('1710034065'))
        self.assertTrue(es_cedula_valida('1116018159'))
        self.assertTrue(es_cedula_valida('1908301664'))

    def test_cedula_invalida(self):
        self.assertFalse(es_cedula_valida('1710034060'))  # dígito malo
        self.assertFalse(es_cedula_valida('171003406'))   # 9 dígitos
        self.assertFalse(es_cedula_valida('17100340655'))  # 11 dígitos
        self.assertFalse(es_cedula_valida('2510034065'))   # provincia inválida
        self.assertFalse(es_cedula_valida('1718034065'))   # 3er dígito inválido
        self.assertFalse(es_cedula_valida('abcde12345'))
        self.assertFalse(es_cedula_valida(''))

    def test_ruc_persona_natural_valido(self):
        self.assertTrue(es_ruc_valido('1710034065001'))
        self.assertTrue(es_ruc_valido('1116018159001'))

    def test_ruc_persona_juridica_valido(self):
        self.assertTrue(es_ruc_valido('1790011674001'))
        self.assertTrue(es_ruc_valido('1792253349001'))

    def test_ruc_sector_publico_valido(self):
        self.assertTrue(es_ruc_valido('1760000017001'))

    def test_ruc_invalido(self):
        self.assertFalse(es_ruc_valido('1710034065000'))  # sufijo 000
        self.assertFalse(es_ruc_valido('1710034064001'))  # cédula con dígito malo
        self.assertFalse(es_ruc_valido('1790011679001'))  # dígito 10 malo
        self.assertFalse(es_ruc_valido('1792253348001'))  # dígito 10 malo
        self.assertFalse(es_ruc_valido('1782253349001'))  # 3er dígito 8
        self.assertFalse(es_ruc_valido('1710034065'))     # solo 10 dígitos
        self.assertFalse(es_ruc_valido(''))

    def test_pasaporte_valido(self):
        self.assertTrue(es_pasaporte_valido('A1234567'))
        self.assertTrue(es_pasaporte_valido('P98765432'))
        self.assertTrue(es_pasaporte_valido('ABCDE'))

    def test_pasaporte_invalido(self):
        self.assertFalse(es_pasaporte_valido('AB'))         # muy corto
        self.assertFalse(es_pasaporte_valido('AB-12345'))   # símbolos
        self.assertFalse(es_pasaporte_valido('A 123456'))   # espacio
        self.assertFalse(es_pasaporte_valido('A' * 21))     # muy largo
        self.assertFalse(es_pasaporte_valido(''))

    def test_validar_identificacion_ok(self):
        self.assertEqual(validar_identificacion('04', '1710034065001'), [])
        self.assertEqual(validar_identificacion('05', '1710034065'), [])
        self.assertEqual(validar_identificacion('06', 'A1234567'), [])

    def test_validar_identificacion_errores(self):
        self.assertEqual(
            validar_identificacion('05', '1710034060'),
            ['La cédula no es válida (dígito verificador incorrecto).'],
        )
        self.assertEqual(
            validar_identificacion('04', '1234567890'),
            ['El RUC debe tener 13 dígitos.'],
        )
        self.assertEqual(
            validar_identificacion('04', ''),
            ['El número de identificación es obligatorio.'],
        )
        self.assertEqual(
            validar_identificacion('06', 'AB-12345'),
            ['El pasaporte solo puede contener letras y números.'],
        )
        self.assertEqual(
            validar_identificacion('06', 'AB'),
            ['El pasaporte tiene un largo inválido.'],
        )


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

    def test_edicion_normaliza_nombres_y_rechaza_descuento_absurdo(self):
        from .forms import OrderEditForm

        pedido = Order.objects.create(vendedor=self.user)
        OrderItem.objects.create(pedido=pedido, producto=self.p1, cantidad=1, precio_unitario=3000)
        pedido.recalcular_totales()  # subtotal $30.00

        form = OrderEditForm(
            data={
                'nombres': 'C l i e n t e',
                'apellidos': 'U n o',
                'metodo_pago': 'efectivo',
                'descuento': '29.999',
                'notas': '',
            },
            instance=pedido,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('2 decimales', form.errors['descuento'][0])

        form = OrderEditForm(
            data={
                'nombres': 'C l i e n t e',
                'apellidos': 'U n o',
                'metodo_pago': 'efectivo',
                'descuento': '1.00',
                'notas': '',
            },
            instance=pedido,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['descuento'], Decimal('1.00'))
        self.assertEqual(pedido.nombres, 'Cliente')
        self.assertEqual(pedido.apellidos, 'Uno')
        self.assertEqual(pedido.cliente, 'Cliente Uno')

    def test_edicion_con_razon_social_para_ruc(self):
        from .forms import OrderEditForm

        pedido = Order.objects.create(
            vendedor=self.user,
            tipo_identificacion='04', identificacion='1710034065001',
        )
        form = OrderEditForm(
            data={
                'razon_social': 'Restaurante XYZ',
                'metodo_pago': 'efectivo',
                'descuento': '0',
                'notas': '',
            },
            instance=pedido,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(pedido.cliente, 'Restaurante XYZ')
        self.assertEqual(pedido.nombres, '')
        self.assertEqual(pedido.apellidos, '')

    def test_edicion_split_nombre_viejo_en_initial(self):
        """Pedidos antiguos (solo nombre completo) se reparten al editar."""
        from .forms import OrderEditForm

        pedido = Order.objects.create(vendedor=self.user, cliente='Josue Gomez')
        form = OrderEditForm(instance=pedido)
        self.assertEqual(form.fields['nombres'].initial, 'Josue')
        self.assertEqual(form.fields['apellidos'].initial, 'Gomez')

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
            {'nombres': 'Cliente', 'apellidos': 'X',
             'metodo_pago': 'efectivo', 'descuento': '0', 'notas': ''},
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
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['total'], '5.00')
        pedido = Order.objects.get(pk=data['pedido_id'])
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_pos_siempre_crea_pedido_pendiente(self):
        """El POS ya no completa ni cobra: queda pendiente para Caja."""
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 1}],
            'completar': 'true',
            'metodo_pago': 'tarjeta',
            'cliente': 'Cliente X',
        })
        self.assertTrue(resp.json()['ok'])
        pedido = Order.objects.get(pk=resp.json()['pedido_id'])
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)
        self.assertEqual(pedido.metodo_pago, Order.METODO_EFECTIVO)
        self.assertEqual(pedido.cliente, '')

    def test_descuento_mayor_al_subtotal_rechazado(self):
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 1}],
            'descuento': '99.00',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])
        self.assertEqual(Order.objects.count(), 0)

    def test_descuento_con_mas_de_2_decimales_rechazado(self):
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 1}],
            'descuento': '1.005',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('2 decimales', resp.json()['error'])
        self.assertEqual(Order.objects.count(), 0)

    def test_descuento_absurdo_rechazado(self):
        self.client.login(username='cajero', password='pass1234')
        resp = self._crear_pedido({
            'items': [{'producto_id': self.p.pk, 'cantidad': 1}],
            'descuento': '111111111111111111.000000000000000111111111',
        })
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['ok'])
        self.assertEqual(Order.objects.count(), 0)

    def test_pos_requiere_login(self):
        resp = self._crear_pedido({'items': [{'producto_id': self.p.pk, 'cantidad': 1}]})
        self.assertEqual(resp.status_code, 302)


class ValidadoresNombreYMontoTests(TestCase):
    """Normalización de nombres y límites de montos (dinero)."""

    # ---------- normalizar_nombre ----------

    def test_letras_sueltas_con_muchos_espacios_se_unen(self):
        self.assertEqual(normalizar_nombre('ca      m   i s a s'), 'camisas')

    def test_todas_letras_sueltas_se_unan_en_una_palabra(self):
        self.assertEqual(normalizar_nombre('c a m i s a s'), 'camisas')

    def test_palabras_reales_se_conservan(self):
        self.assertEqual(normalizar_nombre('Papas Fritas'), 'Papas Fritas')

    def test_letra_suelta_aislada_no_se_pega(self):
        self.assertEqual(
            normalizar_nombre('Hamburguesa a lo especial'),
            'Hamburguesa a lo especial',
        )

    def test_recorta_bordes_y_colapsa_tabs(self):
        self.assertEqual(normalizar_nombre('  Camisas\tGrandes  '), 'Camisas Grandes')

    def test_vacio_y_none(self):
        self.assertEqual(normalizar_nombre(''), '')
        self.assertEqual(normalizar_nombre('   '), '')
        self.assertEqual(normalizar_nombre(None), '')

    def test_errores_nombre(self):
        self.assertEqual(errores_nombre('camisas'), [])
        self.assertEqual(errores_nombre('   '), ['El nombre es obligatorio.'])
        self.assertEqual(errores_nombre(''), ['El nombre es obligatorio.'])

    # ---------- errores_monto ----------

    def test_montos_validos(self):
        self.assertEqual(errores_monto(Decimal('0')), [])
        self.assertEqual(errores_monto(Decimal('2500.00')), [])
        self.assertEqual(errores_monto(Decimal('9999999999.99'), max_int=10), [])

    def test_monto_negativo(self):
        self.assertEqual(
            errores_monto(Decimal('-1')),
            ['El monto no puede ser negativo.'],
        )

    def test_mas_de_2_decimales(self):
        self.assertEqual(
            errores_monto(Decimal('1.005')),
            ['El monto no puede tener más de 2 decimales.'],
        )

    def test_decimales_absurdos_rechazados(self):
        # 111111111111111111,000000000000000111111111
        errores = errores_monto(Decimal('111111111111111111.000000000000000111111111'))
        self.assertIn('El monto no puede tener más de 2 decimales.', errores)
        self.assertIn('El monto no puede superar los 10 dígitos enteros.', errores)

    def test_demasiados_digitos_enteros(self):
        self.assertEqual(
            errores_monto(Decimal('100000000'), max_int=8),
            ['El monto no puede superar los 8 dígitos enteros.'],
        )
        self.assertEqual(
            errores_monto(Decimal('99999999.99'), max_int=8),
            [],
        )

    def test_monto_none(self):
        self.assertEqual(errores_monto(None), ['Ingresá un monto válido.'])
