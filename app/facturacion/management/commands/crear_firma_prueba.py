"""
Genera una firma electrónica de PRUEBA (.p12 autofirmado).

Solo sirve para el ambiente de pruebas (1) del SRI: permite probar el
pipeline completo (XML -> firma -> SOAP) sin tener el certificado real.
El SRI NO aceptará facturas emitidas con esta firma como válidas en
producción.

Uso:
    python manage.py crear_firma_prueba
"""
import datetime as dt
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.conf import settings
from django.core.management.base import BaseCommand

from app.facturacion.models import EmisorConfig

CLAVE_P12 = 'clave1234'


class Command(BaseCommand):
    help = 'Crea una firma electrónica de prueba (.p12 autofirmado) para el ambiente SRI de pruebas.'

    def handle(self, *args, **options):
        from app.orders.validators import es_ruc_valido

        emisor = EmisorConfig.obtener()

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nombre = (emisor.razon_social or 'EMPRESA DE PRUEBA SRI')[:64]
        atributos = [
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'EC'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, nombre),
            x509.NameAttribute(NameOID.COMMON_NAME, nombre),
        ]
        if es_ruc_valido((emisor.ruc or '').strip()):
            # Embebe el RUC en el sujeto, como las firmas reales del SRI;
            # la guarda de emisión exige que la firma coincida con el RUC.
            atributos.append(
                x509.NameAttribute(NameOID.SERIAL_NUMBER, f'RUC: {emisor.ruc}')
            )
        subject = x509.Name(atributos)
        ahora = dt.datetime.now(dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(ahora - dt.timedelta(days=1))
            .not_valid_after(ahora + dt.timedelta(days=365 * 5))
            .sign(key, hashes.SHA256())
        )

        destino_dir = settings.MEDIA_ROOT / 'firmas'
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = Path(destino_dir) / 'firma_prueba.p12'

        p12 = pkcs12.serialize_key_and_certificates(
            name=b'firma_prueba',
            key=key,
            cert=cert,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(
                CLAVE_P12.encode('utf-8')
            ),
        )
        destino.write_bytes(p12)

        emisor.firma.name = 'firmas/firma_prueba.p12'
        emisor.clave_firma = CLAVE_P12
        emisor.ambiente = EmisorConfig.AMBIENTE_PRUEBAS
        emisor.save(update_fields=['firma', 'clave_firma', 'ambiente', 'actualizado'])

        self.stdout.write(self.style.SUCCESS(
            f'\nOK - Firma de prueba creada: {destino}\n'
            f'  - RUC: {emisor.ruc} (placeholder, no es un RUC real)\n'
            f'  - Clave del .p12: {CLAVE_P12}\n'
            '  - Ambiente: 1 (pruebas)\n\n'
            'ADVERTENCIA: esta firma solo sirve para probar. Cuando tengas '
            'la firma real del SRI, cargala en el panel de administración '
            'y cambiá el RUC.\n'
        ))
