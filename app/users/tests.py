from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile


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
