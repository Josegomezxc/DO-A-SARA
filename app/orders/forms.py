"""Formularios del módulo de pedidos."""
from decimal import Decimal

from django import forms

from app.orders.validators import errores_monto, normalizar_nombre

from .models import Order


MONTO_MAX_INT = 10  # max_digits=12 en el modelo -> 10 enteros + 2 decimales


class OrderEditForm(forms.ModelForm):
    """Edición de pedidos pendientes con nombres/apellidos separados.

    Para personas (cédula/pasaporte) se piden Nombres y Apellidos; para
    empresas (RUC) se usa Razón social. En todos los casos el campo
    `cliente` del pedido queda con el nombre completo.
    """

    nombres = forms.CharField(
        label='Nombres', required=False, max_length=60,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '60'}),
    )
    apellidos = forms.CharField(
        label='Apellidos', required=False, max_length=60,
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '60'}),
    )
    razon_social = forms.CharField(
        label='Razón social', required=False, max_length=120,
        help_text='Solo si el cliente es una empresa (RUC).',
        widget=forms.TextInput(attrs={'class': 'form-control', 'maxlength': '120'}),
    )

    class Meta:
        model = Order
        fields = ['nombres', 'apellidos', 'razon_social', 'metodo_pago', 'descuento', 'notas']
        widgets = {
            'metodo_pago': forms.Select(attrs={'class': 'form-control'}),
            'descuento': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0',
                'data-validar': 'numero maxval',
                'data-validar-max-int': str(MONTO_MAX_INT),
                'data-validar-max-dec': '2',
            }),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance and instance.pk:
            if instance.nombres or instance.apellidos:
                self.fields['nombres'].initial = instance.nombres
                self.fields['apellidos'].initial = instance.apellidos
            elif instance.tipo_identificacion == '04':
                self.fields['razon_social'].initial = instance.cliente
            elif instance.cliente:
                # Datos viejos (un solo campo completo): la última palabra
                # va a Apellidos y el resto a Nombres.
                partes = instance.cliente.split()
                if len(partes) > 1:
                    self.fields['apellidos'].initial = partes.pop()
                    self.fields['nombres'].initial = ' '.join(partes)
                else:
                    self.fields['nombres'].initial = instance.cliente
            self.fields['descuento'].widget.attrs['data-validar-max-val'] = \
                f'{instance.subtotal:.2f}'
        self.fields['descuento'].error_messages.update({
            'invalid': 'Ingresá un descuento válido.',
            'max_digits': 'El descuento no puede superar los 10 dígitos enteros.',
            'max_whole_digits': 'El descuento no puede superar los 10 dígitos enteros.',
            'max_decimal_places': 'El descuento no puede tener más de 2 decimales.',
        })

    def clean_descuento(self):
        descuento = self.cleaned_data.get('descuento') or Decimal('0')
        errores = errores_monto(descuento, max_int=MONTO_MAX_INT)
        if errores:
            raise forms.ValidationError(errores[0])
        return descuento

    def clean(self):
        cleaned = super().clean()
        nombres = normalizar_nombre(cleaned.get('nombres'))
        apellidos = normalizar_nombre(cleaned.get('apellidos'))
        razon = normalizar_nombre(cleaned.get('razon_social'))
        if razon:
            # construct_instance sobreescribe los campos con cleaned_data
            # después de clean(): por eso se normaliza aquí también.
            cleaned['nombres'] = ''
            cleaned['apellidos'] = ''
            cleaned['razon_social'] = razon
            self.instance.cliente = razon
        else:
            cleaned['nombres'] = nombres
            cleaned['apellidos'] = apellidos
            self.instance.cliente = f'{nombres} {apellidos}'.strip()[:120]
        descuento = cleaned.get('descuento') or Decimal('0')
        if self.instance and self.instance.pk and descuento > self.instance.subtotal:
            raise forms.ValidationError(
                f'El descuento (${descuento}) no puede ser mayor al subtotal '
                f'(${self.instance.subtotal}).'
            )
        return cleaned
