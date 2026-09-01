from django.urls import path
from .views import accesos, accesos_ajax, exportar_accesos_csv


urlpatterns = [
    path('', accesos, name='accesos'),
    path('ajax/', accesos_ajax, name='accesos_ajax'),
    path('exportar-csv/', exportar_accesos_csv, name='exportar_accesos_csv'),
]