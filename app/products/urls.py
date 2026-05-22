from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    # Productos
    path('', views.ProductListView.as_view(), name='product_list'),
    path('nuevo/', views.ProductCreateView.as_view(), name='product_create'),
    path('<int:pk>/editar/', views.ProductUpdateView.as_view(), name='product_update'),
    path('<int:pk>/desactivar/', views.ProductDeleteView.as_view(), name='product_delete'),
    path('<int:pk>/reactivar/', views.ProductActivateView.as_view(), name='product_activate'),

    # Categorías
    path('categorias/', views.CategoryListView.as_view(), name='category_list'),
    path('categorias/nueva/', views.CategoryCreateView.as_view(), name='category_create'),
    path('categorias/<int:pk>/editar/', views.CategoryUpdateView.as_view(), name='category_update'),
    path('categorias/<int:pk>/desactivar/', views.CategoryDeleteView.as_view(), name='category_delete'),
    path('categorias/<int:pk>/reactivar/', views.CategoryActivateView.as_view(), name='category_activate'),
]
