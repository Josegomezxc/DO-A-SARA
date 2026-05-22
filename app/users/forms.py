"""Formularios de usuarios."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

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


class EmpleadoCreateForm(UserCreationForm):
    rol = forms.ChoiceField(
        choices=Profile.ROL_CHOICES,
        initial=Profile.ROL_EMPLEADO,
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    telefono = forms.CharField(
        required=False, max_length=30, label='Teléfono',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    documento = forms.CharField(
        required=False, max_length=30, label='Documento',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    email = forms.EmailField(
        required=False, label='Correo',
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
    first_name = forms.CharField(
        required=False, label='Nombre',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        required=False, label='Apellido',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'password1', 'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('username', 'password1', 'password2'):
            self.fields[name].widget.attrs.update({'class': 'form-control'})

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile = user.profile
            profile.rol = self.cleaned_data.get('rol', Profile.ROL_EMPLEADO)
            profile.telefono = self.cleaned_data.get('telefono', '')
            profile.documento = self.cleaned_data.get('documento', '')
            profile.save()
        return user


class EmpleadoEditForm(forms.ModelForm):
    rol = forms.ChoiceField(
        choices=Profile.ROL_CHOICES, label='Rol',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )
    telefono = forms.CharField(
        required=False, max_length=30, label='Teléfono',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    documento = forms.CharField(
        required=False, max_length=30, label='Documento',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'is_active')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_active': 'Activo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            profile = getattr(self.instance, 'profile', None)
            if profile:
                self.fields['rol'].initial = profile.rol
                self.fields['telefono'].initial = profile.telefono
                self.fields['documento'].initial = profile.documento

    def save(self, commit=True):
        user = super().save(commit=commit)
        profile = user.profile
        profile.rol = self.cleaned_data['rol']
        profile.telefono = self.cleaned_data.get('telefono', '')
        profile.documento = self.cleaned_data.get('documento', '')
        profile.activo = user.is_active
        if commit:
            profile.save()
        return user
