"""
Verifica la conexión con los servicios web del SRI (Recepción y
Autorización) para el ambiente configurado.

Uso:
    python manage.py test_sri
"""
from django.core.management.base import BaseCommand

from app.facturacion.models import EmisorConfig
from app.facturacion.sri import servicio_sri


class Command(BaseCommand):
    help = 'Comprueba la conexión con los WS del SRI (recepción y autorización).'

    def handle(self, *args, **options):
        emisor = EmisorConfig.obtener()
        self.stdout.write(
            f'\nComprobando ambiente {emisor.ambiente} '
            f'({"pruebas" if emisor.ambiente == "1" else "producción"})...\n'
        )

        for nombre, wsdl in (
            ('Recepción', servicio_sri.WSDL_RECEPCION),
            ('Autorización', servicio_sri.WSDL_AUTORIZACION),
        ):
            url = wsdl[emisor.ambiente]
            self.stdout.write(f'  - {nombre}: {url}')
            try:
                cliente = servicio_sri._cliente(url, emisor.ambiente)
                getattr(
                    cliente.service,
                    'validarComprobante' if nombre == 'Recepción'
                    else 'autorizacionComprobante',
                )
                self.stdout.write(self.style.SUCCESS('    ✓ WSDL descargado y cliente OK'))
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.ERROR(f'    ✗ Error: {exc}'))

        self.stdout.write('')
