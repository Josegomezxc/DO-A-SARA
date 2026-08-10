from django.urls import path

from . import views

app_name = 'orders'

urlpatterns = [
    # POS
    path('pos/', views.POSView.as_view(), name='pos'),
    path('pos/crear/', views.pos_crear_pedido, name='pos_crear'),

    # Pedidos
    path('', views.OrderListView.as_view(), name='order_list'),
    path('<int:pk>/', views.OrderDetailView.as_view(), name='order_detail'),
    path('<int:pk>/editar/', views.OrderUpdateView.as_view(), name='order_update'),
    path('<int:pk>/ticket/', views.order_ticket, name='order_ticket'),
    path('<int:pk>/cancelar/', views.order_cancelar, name='order_cancelar'),
]
