from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('dashboard.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('validacion/',include('validacion.urls')),
    path('accesos/',include('accesos.urls')),
    path('alertas/',include('alertas.urls')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )