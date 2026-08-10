"""
Reintenta el envío de facturas pendientes y consulta la autorización de
las enviadas. Pensado para ejecutarse periódicamente (cron/task).

Uso:
    python manage.py facturacion_pendientes
"""
from django.core.management.base import BaseCommand

from app.facturacion.models import Comprobante
from app.facturacion.sri.emision import reenviar_pendientes


class Command(BaseCommand):
    help = 'Reintenta facturas pendientes y consulta autorizaciones del SRI.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--solo-consultar', action='store_true',
            help='Solo consulta autorizaciones de comprobantes enviados.',
        )

    def handle(self, *args, **options):
        pendientes = Comprobante.objects.filter(
            estado=Comprobante.ESTADO_PENDIENTE
        ).count()
        enviadas = Comprobante.objects.filter(
            estado=Comprobante.ESTADO_ENVIADA
        ).count()
        self.stdout.write(
            f'Pendientes de envío: {pendientes} · Enviadas sin autorizar: {enviadas}'
        )

        reintentados, consultados = reenviar_pendientes(
            consultar=not options['solo_consultar']
        )
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Reintentadas: {reintentados} · Autorizaciones consultadas: {consultados}'
        ))
