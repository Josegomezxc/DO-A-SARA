from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile


class VerificarUsuarioTests(TestCase):
    """API JSON usada por la validación en tiempo real del formulario."""

    def setUp(self):
        User.objects.create_user(username='juan', password='juan12345')

    def test_disponible(self):
        resp = self.client.get(reverse('users:verificar_usuario'), {'username': 'nuevo1'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'disponible': True})

    def test_usado(self):
        resp = self.client.get(reverse('users:verificar_usuario'), {'username': 'juan'})
        self.assertEqual(resp.json(), {'disponible': False, 'motivo': 'usado'})

    def test_usado_ignora_mayusculas(self):
        resp = self.client.get(reverse('users:verificar_usuario'), {'username': 'JUAN'})
        self.assertEqual(resp.json(), {'disponible': False, 'motivo': 'usado'})

    def test_reservado(self):
        resp = self.client.get(reverse('users:verificar_usuario'), {'username': 'admin'})
        self.assertEqual(resp.json(), {'disponible': False, 'motivo': 'reservado'})

    def test_formato_invalido(self):
        resp = self.client.get(reverse('users:verificar_usuario'), {'username': 'ab'})
        self.assertEqual(resp.json(), {'disponible': False, 'motivo': 'formato'})
        resp = self.client.get(reverse('users:verificar_usuario'), {'username': 'espa cio'})
        self.assertEqual(resp.json(), {'disponible': False, 'motivo': 'formato'})

    def test_vacio(self):
        resp = self.client.get(reverse('users:verificar_usuario'))
        self.assertEqual(resp.json(), {'disponible': False, 'motivo': 'vacio'})


class UsersTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin', password='admin12345', email='a@a.com'
        )
        self.empleado = User.objects.create_user(
            username='juan', password='juan12345'
        )

    def test_profile_creado_automaticamente(self):
        self.assertTrue(hasattr(self.admin, 'profile'))
        self.assertTrue(hasattr(self.empleado, 'profile'))
        self.assertEqual(self.admin.profile.rol, Profile.ROL_ADMIN)

    def test_login_ok(self):
        ok = self.client.login(username='juan', password='juan12345')
        self.assertTrue(ok)

    def test_dashboard_requiere_login(self):
        resp = self.client.get(reverse('users:dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_empleado_list_solo_admin(self):
        self.client.login(username='juan', password='juan12345')
        resp = self.client.get(reverse('users:empleado_list'))
        self.assertEqual(resp.status_code, 302)
        self.client.login(username='admin', password='admin12345')
        resp = self.client.get(reverse('users:empleado_list'))
        self.assertEqual(resp.status_code, 200)

    def test_perfil_no_permite_autopromoverse(self):
        """Un empleado NO puede subir su rol a admin desde su perfil."""
        self.client.login(username='juan', password='juan12345')
        resp = self.client.post(reverse('users:perfil'), {
            'first_name': 'Juan',
            'last_name': 'Perez',
            'email': 'juan@ejemplo.com',
            'rol': Profile.ROL_ADMIN,  # intento de escalada
        })
        self.assertEqual(resp.status_code, 302)
        self.empleado.profile.refresh_from_db()
        self.assertEqual(self.empleado.profile.rol, Profile.ROL_EMPLEADO)
        self.assertFalse(self.empleado.is_superuser)

    def test_perfil_no_permite_autodesactivarse(self):
        self.client.login(username='juan', password='juan12345')
        resp = self.client.post(reverse('users:perfil'), {
            'first_name': 'Juan',
            'last_name': '',
            'email': '',
            'is_active': '',  # intento de desactivación
        })
        self.assertEqual(resp.status_code, 302)
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.is_active)

    def test_login_bloqueado_tras_intentos_fallidos(self):
        """Tras N intentos fallidos, el login se bloquea con cooldown."""
        from django.conf import settings
        from django.contrib.messages import get_messages
        from django.core.cache import cache

        cache.clear()
        max_intentos = getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5)
        for _ in range(max_intentos):
            self.client.post(reverse('users:login'), {
                'username': 'juan', 'password': 'incorrecta',
            })

        # Un intento más (fallido) queda bloqueado, no vuelve a validar credenciales
        resp = self.client.post(reverse('users:login'), {
            'username': 'juan', 'password': 'otra-incorrecta',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('users:login'))
        mensajes = list(get_messages(resp.wsgi_request))
        self.assertTrue(any('Demasiados intentos' in str(m) for m in mensajes))
        cache.clear()
