"""Vistas del módulo de facturación electrónica (solo administradores).

El panel replica en el proyecto las páginas que antes solo existían en
el admin de Django: detalle de comprobante, logs SRI, secuencias y la
edición de la configuración del emisor.
"""
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.views.generic import (
    DetailView, FormView, ListView,
)

from app.facturacion.models import Comprobante, EmisorConfig
from app.facturacion.sri import emision as sri_emision
from app.users.decorators import AdminRequiredMixin, admin_required

from .forms import EmisorConfigForm
from .models import LogSri, SecuenciaFactura


class ComprobanteListView(AdminRequiredMixin, ListView):
    """Listado de comprobantes con resumen y acciones."""

    model = Comprobante
    template_name = 'facturacion/comprobante_list.html'
    context_object_name = 'comprobantes'
    paginate_by = 12

    def get_queryset(self):
        qs = Comprobante.objects.select_related('pedido', 'pedido__vendedor')
        q = self.request.GET.get('q', '').strip()
        estado = self.request.GET.get('estado', '').strip()
        if q:
            qs = qs.filter(
                Q(clave_acceso__icontains=q) |
                Q(numero_completo__icontains=q) |
                Q(pedido__numero__icontains=q) |
                Q(pedido__cliente__icontains=q)
            )
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        resumen = Comprobante.objects.aggregate(
            total=Count('id'),
            pendientes=Count('id', filter=Q(estado=Comprobante.ESTADO_PENDIENTE)),
            enviadas=Count('id', filter=Q(estado=Comprobante.ESTADO_ENVIADA)),
            autorizadas=Count('id', filter=Q(estado=Comprobante.ESTADO_AUTORIZADA)),
            rechazadas=Count('id', filter=Q(estado=Comprobante.ESTADO_RECHAZADA)),
        )
        resumen['monto_no_autorizado'] = sri_emision.total_pendiente_monto()
        emisor = EmisorConfig.obtener()
        ctx.update({
            'resumen': resumen,
            'emisor': emisor,
            'q': self.request.GET.get('q', ''),
            'estado': self.request.GET.get('estado', ''),
            'estados': Comprobante.ESTADO_CHOICES,
            'ambiente_nombre': (
                'Pruebas' if emisor.ambiente == EmisorConfig.AMBIENTE_PRUEBAS
                else 'Producción'
            ),
        })
        return ctx


@admin_required
@require_POST
def comprobante_reenviar(request, pk):
    """Reintenta el envío de un comprobante pendiente."""
    comp = get_object_or_404(Comprobante, pk=pk)
    if comp.estado != Comprobante.ESTADO_PENDIENTE:
        messages.warning(request, f'El comprobante {comp.numero} no está pendiente de envío.')
        return redirect('facturacion:comprobante_list')
    try:
        sri_emision._enviar_y_autorizar(comp)
        messages.success(request, f'Comprobante {comp.numero} reenviado: {comp.get_estado_display()}.')
    except Exception:  # noqa: BLE001
        messages.error(request, f'No se pudo reenviar {comp.numero}. Revisá los logs SRI.')
    return redirect('facturacion:comprobante_list')


@admin_required
@require_POST
def comprobante_consultar(request, pk):
    """Consulta la autorización de un comprobante enviado."""
    comp = get_object_or_404(Comprobante, pk=pk)
    if comp.estado != Comprobante.ESTADO_ENVIADA:
        messages.warning(request, f'El comprobante {comp.numero} no está esperando autorización.')
        return redirect('facturacion:comprobante_list')
    sri_emision._consultar_autorizacion(comp, EmisorConfig.obtener())
    messages.success(request, f'Autorización consultada: {comp.get_estado_display()}.')
    return redirect('facturacion:comprobante_list')


@admin_required
@require_POST
def comprobante_eliminar(request, pk):
    """Elimina un comprobante no autorizado y libera el pedido.

    Los logs SRI se borran solos (CASCADE). La clave de acceso y el
    secuencial del pedido se limpian para que la reemisión sea limpia.
    """
    comp = get_object_or_404(Comprobante, pk=pk)
    if comp.estado == Comprobante.ESTADO_AUTORIZADA:
        messages.warning(request, 'No se puede eliminar un comprobante autorizado.')
        return redirect('facturacion:comprobante_list')
    numero = comp.numero
    pedido = comp.pedido
    comp.delete()
    pedido.clave_acceso = None
    pedido.secuencial_factura = None
    pedido.save(update_fields=['clave_acceso', 'secuencial_factura', 'actualizado'])
    messages.success(
        request,
        f'Comprobante {numero} eliminado. El pedido {pedido.numero} '
        'podrá facturarse de nuevo.',
    )
    return redirect('facturacion:comprobante_list')


@admin_required
def comprobante_xml(request, pk):
    """Descarga el XML (firmado o autorizado) del comprobante."""
    comp = get_object_or_404(Comprobante, pk=pk)
    xml = comp.xml_autorizado or comp.xml_firmado
    if not xml:
        return HttpResponse('Sin XML.', status=404)
    nombre = f'{comp.clave_acceso}.xml'
    response = HttpResponse(xml, content_type='application/xml; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return response


@admin_required
def comprobante_pdf(request, pk):
    """Muestra/descarga el PDF A4 imprimible de la factura."""
    from app.facturacion.sri.pdf import generar_pdf

    comp = get_object_or_404(Comprobante, pk=pk)
    pdf = generar_pdf(comp)
    nombre = f'factura_{comp.numero}.pdf'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{nombre}"'
    return response


class ComprobanteDetailView(AdminRequiredMixin, DetailView):
    """Detalle completo de un comprobante (mensajes, XML y logs)."""

    model = Comprobante
    template_name = 'facturacion/comprobante_detail.html'
    context_object_name = 'comp'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['logs'] = self.object.logs.order_by('-creado')[:50]
        return ctx


class LogSriListView(AdminRequiredMixin, ListView):
    """Bitácora de eventos del SRI (reemplaza al admin)."""

    model = LogSri
    template_name = 'facturacion/log_list.html'
    context_object_name = 'logs'
    paginate_by = 25

    def get_queryset(self):
        qs = LogSri.objects.select_related('comprobante').order_by('-creado')
        nivel = self.request.GET.get('nivel', '').strip()
        if nivel in dict(LogSri.NIVEL_CHOICES):
            qs = qs.filter(nivel=nivel)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(mensaje__icontains=q) |
                Q(comprobante__clave_acceso__icontains=q) |
                Q(comprobante__numero_completo__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['niveles'] = LogSri.NIVEL_CHOICES
        ctx['nivel'] = self.request.GET.get('nivel', '')
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class SecuenciaListView(AdminRequiredMixin, ListView):
    """Secuenciales de facturación por año (solo lectura)."""

    model = SecuenciaFactura
    template_name = 'facturacion/secuencia_list.html'
    context_object_name = 'secuencias'
    ordering = ['-anio']


class ConfigFacturacionView(AdminRequiredMixin, FormView):
    """Edición de la configuración del emisor dentro del proyecto."""

    template_name = 'facturacion/config.html'
    form_class = EmisorConfigForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = EmisorConfig.obtener()
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Configuración de facturación guardada.')
        return redirect('facturacion:config')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        emisor = EmisorConfig.obtener()
        ctx['emisor'] = emisor
        ctx['ambiente_nombre'] = (
            'Pruebas' if emisor.ambiente == EmisorConfig.AMBIENTE_PRUEBAS
            else 'Producción'
        )
        return ctx
