from django.urls import path

from . import views

app_name = 'facturacion'

urlpatterns = [
    path('', views.ComprobanteListView.as_view(), name='comprobante_list'),
    path('comprobante/<int:pk>/', views.ComprobanteDetailView.as_view(), name='comprobante_detail'),
    path('logs/', views.LogSriListView.as_view(), name='log_list'),
    path('secuencias/', views.SecuenciaListView.as_view(), name='secuencia_list'),
    path('config/', views.ConfigFacturacionView.as_view(), name='config'),
    path('<int:pk>/reenviar/', views.comprobante_reenviar, name='comprobante_reenviar'),
    path('<int:pk>/consultar/', views.comprobante_consultar, name='comprobante_consultar'),
    path('<int:pk>/eliminar/', views.comprobante_eliminar, name='comprobante_eliminar'),
    path('<int:pk>/xml/', views.comprobante_xml, name='comprobante_xml'),
    path('<int:pk>/pdf/', views.comprobante_pdf, name='comprobante_pdf'),
]
