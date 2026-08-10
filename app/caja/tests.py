"""Tests del módulo Caja (cobro y facturación)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from app.orders.models import Cliente, Order, OrderItem
from app.products.models import Category, Product


class CajaTests(TestCase):
    def setUp(self):
        self.emp = User.objects.create_user(username='cajero', password='pass1234')
        cat = Category.objects.create(nombre='Bebidas')
        self.p = Product.objects.create(nombre='Cola', categoria=cat, precio=Decimal('1.00'))
        self.client.login(username='cajero', password='pass1234')

    def _pedido_pendiente(self, **extra):
        pedido = Order.objects.create(vendedor=self.emp, **extra)
        OrderItem.objects.create(
            pedido=pedido, producto=self.p, cantidad=2, precio_unitario=self.p.precio,
        )
        pedido.recalcular_totales()
        return pedido

    def _cobrar(self, pedido, follow=False, **extra):
        data = {
            'metodo_pago': 'efectivo',
            'recibido': '10.00',
            'tipo_identificacion': '07',
        }
        data.update(extra)
        return self.client.post(
            reverse('caja:caja_completar', args=[pedido.pk]), data=data, follow=follow,
        )

    # ---------- Permisos ----------

    def test_anonimo_redirige_login(self):
        self.client.logout()
        resp = self.client.get(reverse('caja:index'))
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse('caja:caja_detalle', args=[1]))
        self.assertEqual(resp.status_code, 302)

    def test_empleado_accede_a_caja(self):
        resp = self.client.get(reverse('caja:index'))
        self.assertEqual(resp.status_code, 200)

    # ---------- Búsqueda por ticket ----------

    def test_buscar_por_numero_redirige_al_detalle(self):
        pedido = self._pedido_pendiente()
        resp = self.client.get(reverse('caja:index'), {'q': pedido.numero})
        self.assertRedirects(resp, reverse('caja:caja_detalle', args=[pedido.pk]))

    def test_buscar_sin_resultado_muestra_mensaje(self):
        resp = self.client.get(reverse('caja:index'), {'q': 'P-99999999-99999'}, follow=True)
        self.assertContains(resp, 'No se encontró ningún pedido con')

    def test_buscar_cobrado_muestra_mensaje_sin_redirigir(self):
        pedido = self._pedido_pendiente()
        pedido.completar(usuario=self.emp)
        resp = self.client.get(reverse('caja:index'), {'q': pedido.numero}, follow=True)
        self.assertContains(resp, f'{pedido.numero} ya fue cobrado')
        self.assertEqual(
            resp.redirect_chain[-1][0],
            reverse('caja:index'),
        )

    # ---------- Listado con todos los estados ----------

    def test_index_muestra_todos_los_estados(self):
        pendiente = self._pedido_pendiente()
        cobrado = self._pedido_pendiente()
        cobrado.completar(usuario=self.emp)
        cancelado = self._pedido_pendiente()
        cancelado.cancelar()

        resp = self.client.get(reverse('caja:index'))

        self.assertContains(resp, pendiente.numero)
        self.assertContains(resp, cobrado.numero)
        self.assertContains(resp, cancelado.numero)
        self.assertContains(resp, 'badge-warning">Pendiente')
        self.assertContains(resp, 'badge-success">Cobrado')
        self.assertContains(resp, 'badge-danger">Cancelado')
        self.assertContains(resp, '1 pendientes')
        self.assertContains(resp, '1 cobrados')
        self.assertContains(resp, '1 cancelados')

    # ---------- Detalle ----------

    def test_detalle_solo_pedidos_pendientes(self):
        pedido = self._pedido_pendiente()
        resp = self.client.get(reverse('caja:caja_detalle', args=[pedido.pk]))
        self.assertEqual(resp.status_code, 200)
        pedido.completar(usuario=self.emp)
        resp = self.client.get(reverse('caja:caja_detalle', args=[pedido.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_ticket_visible_para_cualquier_empleado(self):
        """La cajera ve el ticket aunque el pedido sea de otro vendedor."""
        otro = User.objects.create_user(username='otro', password='pass1234')
        pedido = Order.objects.create(vendedor=otro)
        OrderItem.objects.create(
            pedido=pedido, producto=self.p, cantidad=1, precio_unitario=self.p.precio,
        )
        pedido.recalcular_totales()
        resp = self.client.get(reverse('caja:caja_ticket', args=[pedido.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pagar en Caja')

    def test_ticket_visible_para_pedido_cobrado(self):
        """El ticket de un pedido cobrado sigue siendo imprimible desde caja."""
        pedido = self._pedido_pendiente()
        pedido.completar(usuario=self.emp)
        resp = self.client.get(reverse('caja:caja_ticket', args=[pedido.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, pedido.get_metodo_pago_display())
        self.assertNotContains(resp, 'Pagar en Caja')

    # ---------- Cobro ----------

    def test_completa_y_guarda_datos(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            metodo_pago='tarjeta', recibido='',
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion='1710034065',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse('caja:index'))
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.metodo_pago, 'tarjeta')
        self.assertEqual(pedido.cliente, 'Ana Pérez')
        self.assertEqual(pedido.nombres, 'Ana')
        self.assertEqual(pedido.apellidos, 'Pérez')
        self.assertEqual(pedido.tipo_identificacion, '05')
        self.assertEqual(pedido.identificacion, '1710034065')

    def test_consumidor_final_autocompleta_datos(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(pedido)
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.cliente, 'CONSUMIDOR FINAL')
        self.assertEqual(pedido.identificacion, '9999999999999')
        self.assertEqual(pedido.tipo_identificacion, '07')

    def test_pasaporte_largo_invalido_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='06', identificacion='AB',
            nombres='Viajero', apellidos='Anónimo',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El pasaporte tiene un largo inválido')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_falta_identificacion_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='05',
            nombres='Ana', apellidos='Pérez', identificacion='',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El número de identificación es obligatorio')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_falta_nombres_o_apellidos_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='05',
            nombres='Ana', apellidos='', identificacion='1710034065',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Debe ingresar los nombres y apellidos del cliente')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_falta_razon_social_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='04', razon_social='',
            identificacion='1710034065001',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'La razón social del cliente es obligatoria')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_recibido_no_numerico_rechazado(self):
        pedido = self._pedido_pendiente()  # total $2.00
        resp = self._cobrar(pedido, recibido='abc')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'monto recibido válido')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_recibido_absurdo_rechazado(self):
        """111111111111111111.000000000000000111111111 -> decimales de más."""
        pedido = self._pedido_pendiente()  # total $2.00
        resp = self._cobrar(
            pedido, recibido='111111111111111111.000000000000000111111111',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '2 decimales')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_cliente_se_normaliza_al_guardar(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            metodo_pago='tarjeta', recibido='',
            tipo_identificacion='05', identificacion='1710034065',
            nombres='J u a n', apellidos='P é r e z',
        )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.nombres, 'Juan')
        self.assertEqual(pedido.apellidos, 'Pérez')
        self.assertEqual(pedido.cliente, 'Juan Pérez')

    def test_error_repopula_el_formulario(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion='1710034065', email='mal@',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'value="Ana"')
        self.assertContains(resp, 'value="Pérez"')
        self.assertContains(resp, 'value="1710034065"')
        self.assertContains(resp, 'value="mal@"')

    # ---------- Validación de identificaciones (SRI) ----------

    def test_cedula_digito_malo_rechazada(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='05',
            nombres='Ana', apellidos='Pérez', identificacion='1710034060',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'La cédula no es válida (dígito verificador incorrecto)')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_ruc_natural_aceptado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='04', razon_social='Restaurante XYZ',
            identificacion='1710034065001',
        )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)
        self.assertEqual(pedido.identificacion, '1710034065001')
        self.assertEqual(pedido.cliente, 'Restaurante XYZ')
        self.assertEqual(pedido.nombres, '')
        self.assertEqual(pedido.apellidos, '')

    def test_ruc_juridica_aceptado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='04', razon_social='Empresa SA',
            identificacion='1790011674001',
        )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)

    def test_ruc_invalido_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='04', razon_social='Empresa SA',
            identificacion='1710034064001',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El RUC no es válido (dígito verificador incorrecto)')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_ruc_largo_malo_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='04', razon_social='Empresa SA',
            identificacion='1234567890',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El RUC debe tener 13 dígitos')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_pasaporte_valido_aceptado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='06',
            nombres='Viajero', apellidos='Anónimo', identificacion='A1234567',
        )
        self.assertEqual(resp.status_code, 302)
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_COMPLETADO)

    def test_pasaporte_con_simbolos_rechazado(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido, tipo_identificacion='06',
            nombres='Viajero', apellidos='Anónimo', identificacion='AB-12345',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'El pasaporte solo puede contener letras y números')
        pedido.refresh_from_db()
        self.assertEqual(pedido.estado, Order.ESTADO_PENDIENTE)

    def test_no_se_cobra_pedido_ya_completado(self):
        pedido = self._pedido_pendiente()
        pedido.completar(usuario=self.emp)
        resp = self._cobrar(pedido)
        self.assertEqual(resp.status_code, 404)

    def test_mensaje_success_tras_cobrar(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(pedido, follow=True)
        self.assertContains(resp, 'Cobrado')


class ClienteHabitualTests(TestCase):
    """Guardado y búsqueda de clientes habituales (por identificación)."""

    CEDULA = '1710034065'
    RUC = '1710034065001'

    def setUp(self):
        self.emp = User.objects.create_user(username='cajero', password='pass1234')
        cat = Category.objects.create(nombre='Bebidas')
        self.p = Product.objects.create(nombre='Cola', categoria=cat, precio=Decimal('1.00'))
        self.client.login(username='cajero', password='pass1234')

    def _pedido_pendiente(self, **extra):
        pedido = Order.objects.create(vendedor=self.emp, **extra)
        OrderItem.objects.create(
            pedido=pedido, producto=self.p, cantidad=2, precio_unitario=self.p.precio,
        )
        pedido.recalcular_totales()
        return pedido

    def _cobrar(self, pedido, **extra):
        data = {
            'metodo_pago': 'efectivo',
            'recibido': '10.00',
            'tipo_identificacion': '07',
        }
        data.update(extra)
        return self.client.post(
            reverse('caja:caja_completar', args=[pedido.pk]), data=data,
        )

    def _buscar(self, q=''):
        return self.client.get(reverse('caja:clientes_buscar'), {'q': q})

    # ---------- Guardado al cobrar ----------

    def test_se_guarda_cliente_al_cobrar_con_cedula(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            metodo_pago='tarjeta', recibido='',
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion=self.CEDULA,
            direccion='Av. Siempre Viva', email='ana@mail.com', telefono='0999999999',
        )
        self.assertEqual(resp.status_code, 302)
        cliente = Cliente.objects.get(tipo_identificacion='05', identificacion=self.CEDULA)
        self.assertEqual(cliente.nombre, 'Ana Pérez')
        self.assertEqual(cliente.nombres, 'Ana')
        self.assertEqual(cliente.apellidos, 'Pérez')
        self.assertEqual(cliente.direccion, 'Av. Siempre Viva')
        self.assertEqual(cliente.email, 'ana@mail.com')
        self.assertEqual(cliente.telefono, '0999999999')

    def test_no_se_guarda_consumidor_final(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(pedido)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Cliente.objects.exists())

    def test_se_actualiza_sin_duplicar(self):
        for i in range(2):
            pedido = self._pedido_pendiente()
            resp = self._cobrar(
                pedido,
                metodo_pago='tarjeta', recibido='',
                tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
                identificacion=self.CEDULA,
                email=f'ana{i}@mail.com',
            )
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(Cliente.objects.count(), 1)
        cliente = Cliente.objects.get(identificacion=self.CEDULA)
        self.assertEqual(cliente.email, 'ana1@mail.com')

    def test_no_borra_campos_vacios(self):
        pedido = self._pedido_pendiente()
        self._cobrar(
            pedido,
            metodo_pago='tarjeta', recibido='',
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion=self.CEDULA, direccion='Av. Siempre Viva',
        )
        pedido = self._pedido_pendiente()
        self._cobrar(
            pedido,
            metodo_pago='tarjeta', recibido='',
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion=self.CEDULA,
        )
        cliente = Cliente.objects.get(identificacion=self.CEDULA)
        self.assertEqual(cliente.direccion, 'Av. Siempre Viva')

    def test_ruc_guarda_cliente(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            metodo_pago='tarjeta', recibido='',
            tipo_identificacion='04', razon_social='Restaurante XYZ',
            identificacion=self.RUC,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Cliente.objects.filter(tipo_identificacion='04').exists())

    def test_cobro_invalido_no_guarda_cliente(self):
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion='1710034060',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Cliente.objects.exists())

    # ---------- Búsqueda por identificación ----------

    def test_buscar_por_cedula_devuelve_cliente(self):
        Cliente.objects.create(
            tipo_identificacion='05', identificacion=self.CEDULA, nombre='Ana Pérez',
        )
        resp = self._buscar(self.CEDULA)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['clientes']), 1)
        self.assertEqual(data['clientes'][0]['nombre'], 'Ana Pérez')
        self.assertEqual(data['clientes'][0]['identificacion'], self.CEDULA)
        self.assertIn('nombres', data['clientes'][0])
        self.assertIn('apellidos', data['clientes'][0])

    def test_buscar_parcial_mientras_se_escribe(self):
        Cliente.objects.create(
            tipo_identificacion='05', identificacion=self.CEDULA, nombre='Ana Pérez',
        )
        resp = self._buscar(self.CEDULA[:6])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()['clientes']), 1)

    def test_buscar_por_nombre_no_devuelve_nada(self):
        Cliente.objects.create(
            tipo_identificacion='05', identificacion=self.CEDULA, nombre='Ana Pérez',
        )
        resp = self._buscar('Ana')
        self.assertEqual(resp.json()['clientes'], [])

    def test_buscar_sin_q_devuelve_vacio(self):
        Cliente.objects.create(
            tipo_identificacion='05', identificacion=self.CEDULA, nombre='Ana Pérez',
        )
        resp = self._buscar()
        self.assertEqual(resp.json()['clientes'], [])

    def test_buscar_exacto_primero(self):
        Cliente.objects.create(
            tipo_identificacion='05', identificacion=self.CEDULA, nombre='Ana Exacta',
        )
        Cliente.objects.create(
            tipo_identificacion='05', identificacion='1710034065999', nombre='Otra Ana',
        )
        resp = self._buscar(self.CEDULA)
        clientes = resp.json()['clientes']
        self.assertEqual(clientes[0]['nombre'], 'Ana Exacta')

    def test_buscar_nunca_devuelve_consumidor_final(self):
        Cliente.objects.create(
            tipo_identificacion='07', identificacion='9999999999999',
            nombre='CONSUMIDOR FINAL',
        )
        resp = self._buscar('9999999999')
        self.assertEqual(resp.json()['clientes'], [])

    def test_buscar_requiere_login(self):
        self.client.logout()
        resp = self._buscar(self.CEDULA)
        self.assertEqual(resp.status_code, 302)

    # ---------- Interfaz ----------

    def test_detalle_muestra_buscador_de_cliente(self):
        pedido = self._pedido_pendiente()
        resp = self.client.get(reverse('caja:caja_detalle', args=[pedido.pk]))
        self.assertContains(resp, 'Cliente habitual')
        self.assertContains(resp, 'buscar-cliente')
        self.assertContains(resp, 'switch-factura-datos')

    def test_mensaje_consumidor_no_se_auto_cierra(self):
        """El aviso de CONSUMIDOR FINAL debe ser permanente: main.js
        descarta los .alert que no tengan la clase alert-permanent."""
        pedido = self._pedido_pendiente()
        resp = self.client.get(reverse('caja:caja_detalle', args=[pedido.pk]))
        self.assertContains(
            resp, 'id="receptor-consumidor" class="alert alert-info alert-permanent',
        )

    def test_switch_apagado_por_defecto(self):
        """Sin datos cargados, el switch está apagado (consumidor final)."""
        pedido = self._pedido_pendiente()
        resp = self.client.get(reverse('caja:caja_detalle', args=[pedido.pk]))
        self.assertNotContains(resp, 'switch-factura-datos" checked>')

    def test_switch_encendido_tras_error_con_datos(self):
        """Tras un error con tipo 05, el switch vuelve encendido."""
        pedido = self._pedido_pendiente()
        resp = self._cobrar(
            pedido,
            tipo_identificacion='05', nombres='Ana', apellidos='Pérez',
            identificacion='1710034060',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'switch-factura-datos" checked>')
