"""URL configuration for the Doña Sara project."""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.decorators import login_required
from django.views.generic import RedirectView
from django.views.static import serve as serve_media


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='users:dashboard', permanent=False)),
    path('cuentas/', include('app.users.urls', namespace='users')),
    path('productos/', include('app.products.urls', namespace='products')),
    path('pedidos/', include('app.orders.urls', namespace='orders')),
    path('facturacion/', include('app.facturacion.urls', namespace='facturacion')),
    path('caja/', include('app.caja.urls', namespace='caja')),
]

if settings.DEBUG:
    # runserver sirve los static automáticamente desde STATICFILES_DIRS via finders.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # En producción whitenoise sirve los static; media se sirve desde Django
    # pero SOLO para usuarios autenticados.
    _media_prefix = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(
            rf'^{_media_prefix}(?P<path>.*)$',
            login_required(serve_media),
            {'document_root': settings.MEDIA_ROOT},
            name='media_privada',
        ),
    ]


admin.site.site_header = 'Doña Sara - Administración'
admin.site.site_title = 'Doña Sara Admin'
admin.site.index_title = 'Panel de control'
