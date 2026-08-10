from django.urls import path

from . import views

app_name = 'caja'

urlpatterns = [
    path('', views.CajaIndexView.as_view(), name='index'),
    path('clientes/buscar/', views.clientes_buscar, name='clientes_buscar'),
    path('<int:pk>/', views.CajaDetalleView.as_view(), name='caja_detalle'),
    path('<int:pk>/ticket/', views.caja_ticket, name='caja_ticket'),
    path('<int:pk>/completar/', views.caja_completar, name='caja_completar'),
]
