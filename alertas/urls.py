from django.urls import path
from .views import alertas, alertas_ajax, resolver_alerta, exportar_alertas_csv


urlpatterns = [
    path('', alertas, name='alertas'),
    path('ajax/', alertas_ajax, name='alertas_ajax'),
    path('resolver/<int:acceso_id>/', resolver_alerta, name='resolver_alerta'),
    path('exportar-csv/', exportar_alertas_csv, name='exportar_alertas_csv'),
]