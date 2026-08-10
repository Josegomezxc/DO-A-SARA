"""Formularios del panel de facturación electrónica."""
import re

from django import forms

from app.orders.validators import es_ruc_valido

from .models import EmisorConfig


class EmisorConfigForm(forms.ModelForm):
    """Edición de los datos fiscales del emisor (singleton)."""

    class Meta:
        model = EmisorConfig
        fields = (
            'ruc', 'razon_social', 'nombre_comercial', 'direccion',
            'telefono', 'email', 'obligado_contabilidad', 'agente_retencion',
            'contribuyente_especial', 'ambiente', 'establecimiento',
            'punto_emision', 'firma', 'clave_firma',
        )
        widgets = {
            # render_value: al recargar con error no se pierde la clave.
            'clave_firma': forms.PasswordInput(
                render_value=True,
                attrs={
                    'class': 'form-control',
                    # evita que el navegador ofrezca guardar la clave.
                    'autocomplete': 'new-password',
                },
            ),
            'ruc': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '13'}),
            'razon_social': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '300'},
            ),
            'nombre_comercial': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '300'},
            ),
            'direccion': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '300'},
            ),
            'telefono': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '30'},
            ),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'obligado_contabilidad': forms.CheckboxInput(
                attrs={'class': 'form-check-input'},
            ),
            'agente_retencion': forms.CheckboxInput(
                attrs={'class': 'form-check-input'},
            ),
            'contribuyente_especial': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '13'},
            ),
            'ambiente': forms.Select(attrs={'class': 'form-control'}),
            'establecimiento': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '3'},
            ),
            'punto_emision': forms.TextInput(
                attrs={'class': 'form-control', 'maxlength': '3'},
            ),
            'firma': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
        }

    def clean_ruc(self):
        ruc = (self.cleaned_data.get('ruc') or '').strip()
        if not re.fullmatch(r'\d{13}', ruc):
            raise forms.ValidationError('El RUC debe tener exactamente 13 dígitos.')
        if not es_ruc_valido(ruc):
            raise forms.ValidationError(
                'El RUC no es válido (dígito verificador incorrecto).'
            )
        return ruc

    def clean_establecimiento(self):
        valor = (self.cleaned_data.get('establecimiento') or '').strip()
        if not valor.isdigit() or len(valor) != 3:
            raise forms.ValidationError('Debe tener 3 dígitos (ej: 001).')
        return valor

    def clean_punto_emision(self):
        valor = (self.cleaned_data.get('punto_emision') or '').strip()
        if not valor.isdigit() or len(valor) != 3:
            raise forms.ValidationError('Debe tener 3 dígitos (ej: 001).')
        return valor

    def clean(self):
        """Valida la firma al guardar: clave correcta y RUC coincidente.

        Se ejecuta siempre que haya una firma (recién subida o la ya
        cargada): la abre con la clave del formulario y compara el RUC
        del certificado con el RUC configurado, avisando antes de
        guardar en vez de descubrir el problema al emitir.
        """
        cleaned = super().clean()
        firma_archivo = cleaned.get('firma')
        clave = (cleaned.get('clave_firma') or '').strip()
        if not firma_archivo:
            return cleaned
        if not clave:
            self.add_error(
                'clave_firma',
                'Cargá la clave del archivo .p12 para validar la firma.',
            )
            return cleaned

        from app.facturacion.sri.firma import obtener_ruc_bytes

        try:
            datos = firma_archivo.read()
            ruc_firma = obtener_ruc_bytes(datos, clave)
        except ValueError:
            self.add_error(
                'clave_firma',
                'La clave no coincide con el archivo .p12 de la firma.',
            )
            return cleaned

        if not ruc_firma:
            self.add_error(
                'firma',
                'El certificado del archivo .p12 no contiene un RUC válido.',
            )
            return cleaned

        ruc_config = cleaned.get('ruc') or ''
        if ruc_firma != ruc_config:
            self.add_error(
                'firma',
                f'La firma pertenece al RUC {ruc_firma}, pero la configuración '
                f'usa el RUC {ruc_config}.',
            )
        return cleaned
