"""URLs de la app users."""
from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('buscar/', views.GlobalSearchView.as_view(), name='buscar'),
    path('verificar-usuario/', views.verificar_usuario, name='verificar_usuario'),
    path('perfil/', views.perfil_view, name='perfil'),

    path('empleados/', views.EmpleadoListView.as_view(), name='empleado_list'),
    path('empleados/nuevo/', views.EmpleadoCreateView.as_view(), name='empleado_create'),
    path('empleados/<int:pk>/editar/', views.EmpleadoUpdateView.as_view(), name='empleado_update'),
    path('empleados/<int:pk>/desactivar/', views.EmpleadoDeleteView.as_view(), name='empleado_delete'),
    path('empleados/<int:pk>/reactivar/', views.EmpleadoActivateView.as_view(), name='empleado_activate'),
]
