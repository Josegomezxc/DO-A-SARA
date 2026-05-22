"""URL configuration for the Doña Sara project."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='users:dashboard', permanent=False)),
    path('cuentas/', include('app.users.urls', namespace='users')),
    path('productos/', include('app.products.urls', namespace='products')),
    path('pedidos/', include('app.orders.urls', namespace='orders')),
]

if settings.DEBUG:
    # runserver sirve los static automáticamente desde STATICFILES_DIRS via finders.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


admin.site.site_header = 'Doña Sara - Administración'
admin.site.site_title = 'Doña Sara Admin'
admin.site.index_title = 'Panel de control'
