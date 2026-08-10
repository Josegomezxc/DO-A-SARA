"""Formularios para gestionar el catálogo del menú."""
from django import forms
from django.core.exceptions import ValidationError

from app.orders.validators import errores_monto, errores_nombre, normalizar_nombre

from .models import Category, Product


IMAGEN_EXTENSIONES = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
IMAGEN_MAX_MB = 5
PRECIO_MAX_INT = 8  # max_digits=10 en el modelo -> 8 enteros + 2 decimales


class CategoryForm(forms.ModelForm):
    """Formulario de categorías.

    El campo `orden` NO se pide: se asigna automáticamente en
    Category.save() (siguiente posición disponible).
    """

    class Meta:
        model = Category
        fields = ['nombre', 'descripcion', 'icono', 'color', 'activa']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': '80', 'data-validar': 'requerido',
            }),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'fas fa-hamburger', 'maxlength': '60'}),
            'color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Los nombres con solo espacios deben llegar a clean_nombre
        # (que los rechaza con el mensaje personalizado).
        self.fields['nombre'].strip = False
        self.fields['nombre'].error_messages['required'] = 'El nombre es obligatorio.'

    def clean_nombre(self):
        errores = errores_nombre(self.cleaned_data.get('nombre'))
        if errores:
            raise forms.ValidationError(errores[0])
        return normalizar_nombre(self.cleaned_data.get('nombre'))


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['nombre', 'descripcion', 'categoria', 'precio', 'imagen', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 'maxlength': '140', 'data-validar': 'requerido',
            }),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                 'placeholder': 'Ej: Incluye carne, queso cheddar laminado, lechuga, tomate...'}),
            'categoria': forms.Select(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
                'data-validar': 'numero',
                'data-validar-max-int': str(PRECIO_MAX_INT),
                'data-validar-max-dec': '2',
            }),
            'imagen': forms.ClearableFileInput(attrs={
                'class': 'form-control', 'accept': 'image/*',
                'data-validar': 'imagen',
                'data-validar-imagen-ext': 'jpg,jpeg,png,webp,gif',
                'data-validar-imagen-max': '5',
            }),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['precio'].error_messages.update({
            'invalid': 'Ingresá un precio válido.',
            'max_digits': 'El precio no puede superar los 8 dígitos enteros.',
            'max_whole_digits': 'El precio no puede superar los 8 dígitos enteros.',
            'max_decimal_places': 'El precio no puede tener más de 2 decimales.',
        })

    def clean_nombre(self):
        errores = errores_nombre(self.cleaned_data.get('nombre'))
        if errores:
            raise forms.ValidationError(errores[0])
        return normalizar_nombre(self.cleaned_data.get('nombre'))

    def clean_precio(self):
        precio = self.cleaned_data.get('precio')
        errores = errores_monto(precio, max_int=PRECIO_MAX_INT)
        if errores:
            raise forms.ValidationError(errores[0])
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
