from django.urls import path
from . import views

urlpatterns = [
    path('', views.accesos, name='accesos'),
    path('ajax/', views.accesos_ajax, name='accesos_ajax'),
    path('exportar-csv/', views.exportar_accesos_csv, name='exportar_accesos_csv'),
    path('visita/<int:visita_id>/json/', views.visita_detalle_json, name='visita_detalle_json'),
    path('visita/<int:visita_id>/guardar/', views.visita_guardar_pertenencias, name='visita_guardar_pertenencias'),
    path('visita/<int:visita_id>/analizar-ia/', views.visita_analizar_ia, name='visita_analizar_ia'),
    path('visita/<int:visita_id>/egreso/', views.visita_registrar_egreso_ajax, name='visita_registrar_egreso_ajax'),
    path('visita/crear/', views.visita_crear_ajax, name='visita_crear_ajax'),
]
