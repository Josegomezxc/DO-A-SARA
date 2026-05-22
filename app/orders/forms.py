"""Formularios del módulo de pedidos."""
from decimal import Decimal

from django import forms

from .models import Order


class OrderEditForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['cliente', 'metodo_pago', 'descuento', 'notas']
        widgets = {
            'cliente': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '120'}),
            'metodo_pago': forms.Select(attrs={'class': 'form-control'}),
            'descuento': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def clean_descuento(self):
        descuento = self.cleaned_data.get('descuento') or Decimal('0')
        if descuento < 0:
            raise forms.ValidationError('El descuento no puede ser negativo.')
        return descuento

    def clean(self):
        cleaned = super().clean()
        descuento = cleaned.get('descuento') or Decimal('0')
        if self.instance and self.instance.pk and descuento > self.instance.subtotal:
            raise forms.ValidationError(
                f'El descuento (${descuento}) no puede ser mayor al subtotal '
                f'(${self.instance.subtotal}).'
            )
        return cleaned
