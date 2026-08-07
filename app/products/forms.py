"""Formularios para gestionar el catálogo del menú."""
from django import forms
from django.core.exceptions import ValidationError

from .models import Category, Product


IMAGEN_EXTENSIONES = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
IMAGEN_MAX_MB = 5


class CategoryForm(forms.ModelForm):
    """Formulario de categorías.

    El campo `orden` NO se pide: se asigna automáticamente en
    Category.save() (siguiente posición disponible).
    """

    class Meta:
        model = Category
        fields = ['nombre', 'descripcion', 'icono', 'color', 'activa']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '80'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'fas fa-hamburger', 'maxlength': '60'}),
            'color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre es obligatorio.')
        return nombre


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['nombre', 'descripcion', 'categoria', 'precio', 'imagen', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '140'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                 'placeholder': 'Ej: Incluye carne, queso cheddar laminado, lechuga, tomate...'}),
            'categoria': forms.Select(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'imagen': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre es obligatorio.')
        return nombre

    def clean_precio(self):
        precio = self.cleaned_data.get('precio')
        if precio is None or precio < 0:
            raise forms.ValidationError('El precio no puede ser negativo.')
        return precio

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if not imagen:
            return imagen
        nombre = (imagen.name or '').lower()
        extension = nombre.rsplit('.', 1)[-1] if '.' in nombre else ''
        if extension not in IMAGEN_EXTENSIONES:
            raise ValidationError(
                f'Formato de imagen no permitido. Usá: {", ".join(sorted(IMAGEN_EXTENSIONES))}.'
            )
        if imagen.size > IMAGEN_MAX_MB * 1024 * 1024:
            raise ValidationError(f'La imagen supera el máximo de {IMAGEN_MAX_MB} MB.')
        return imagen
