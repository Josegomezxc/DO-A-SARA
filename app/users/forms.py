"""Formularios de usuarios."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import Profile


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Usuario',
            'autofocus': True,
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control form-control-lg',
            'placeholder': 'Contraseña',
        })


class EmpleadoCreateForm(forms.Form):
    """Formulario simplificado: solo usuario, contraseña y rol."""

    username = forms.CharField(
        label='Usuario',
        min_length=3,
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Nombre de usuario',
            'autocomplete': 'off',
            'data-validar': 'requerido usuario',
        }),
    )
    password = forms.CharField(
        label='Contraseña',
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mínimo 8 caracteres',
            'autocomplete': 'new-password',
            'data-validar': 'requerido password',
        }),
        help_text='Mínimo 8 caracteres. No uses solo números.',
    )
    rol = forms.ChoiceField(
        # Solo se muestran admin y empleado; superowner nunca aparece aquí
        choices=[
            (Profile.ROL_EMPLEADO, 'Empleado'),
            (Profile.ROL_ADMIN, 'Administrador'),
        ],
        initial=Profile.ROL_EMPLEADO,
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['data-validar-disponible'] = \
            reverse('users:verificar_usuario')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError('Ese nombre de usuario ya está en uso.')
        # Bloquear nombres que podrían confundirse con el owner
        reserved = ['owner', 'superowner', 'root', 'admin', 'administrator']
        if username.lower() in reserved:
            raise ValidationError('Ese nombre de usuario está reservado.')
        return username

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        if password.isdigit():
            raise ValidationError('La contraseña no puede ser solo números.')
        return password

    def save(self):
        username = self.cleaned_data['username']
        password = self.cleaned_data['password']
        rol = self.cleaned_data['rol']

        user = User.objects.create_user(username=username, password=password)
        profile = user.profile
        profile.rol = rol
        profile.save()
        return user


class EmpleadoEditForm(forms.ModelForm):
    """Formulario de edición (solo admin): no toca contraseña, solo estado y rol."""

    rol = forms.ChoiceField(
        choices=[
            (Profile.ROL_EMPLEADO, 'Empleado'),
            (Profile.ROL_ADMIN, 'Administrador'),
        ],
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ('is_active',)
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_active': 'Cuenta activa',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            profile = getattr(self.instance, 'profile', None)
            if profile:
                self.fields['rol'].initial = profile.rol

    def save(self, commit=True):
        user = super().save(commit=commit)
        profile = user.profile
        profile.rol = self.cleaned_data['rol']
        profile.activo = user.is_active
        if commit:
            profile.save()
        return user


class PerfilForm(forms.ModelForm):
    """Autoedición del propio perfil.

    NO incluye rol ni is_active: un usuario jamás puede cambiarse su
    propio rol (evita escalada de privilegios) ni desactivarse solo.
    """

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': '150', 'data-validar': 'requerido',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': '150', 'data-validar': 'requerido',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'data-validar': 'email',
            }),
        }
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Email',
        }
