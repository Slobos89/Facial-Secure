from django.urls import path
from . import views

urlpatterns = [
    path('', views.accesos, name='accesos'),
    path('ajax/', views.accesos_ajax, name='accesos_ajax'),
    path('visitas/live/', views.visitas_live_ajax, name='visitas_live_ajax'),
    path('exportar-csv/', views.exportar_accesos_csv, name='exportar_accesos_csv'),
    path('inteligencia/', views.inteligencia_visitas, name='inteligencia_visitas'),
    path('inteligencia/datos/', views.inteligencia_datos_ajax, name='inteligencia_datos_ajax'),
    path('visita/<int:visita_id>/json/', views.visita_detalle_json, name='visita_detalle_json'),
    path('visita/<int:visita_id>/guardar/', views.visita_guardar_pertenencias, name='visita_guardar_pertenencias'),
    path('visita/<int:visita_id>/analizar-ia/', views.visita_analizar_ia, name='visita_analizar_ia'),
    path('visita/<int:visita_id>/egreso/', views.visita_registrar_egreso_ajax, name='visita_registrar_egreso_ajax'),
    path('visita/<int:visita_id>/parlante/', views.visita_emitir_parlante, name='visita_emitir_parlante'),
    path('visita/crear/', views.visita_crear_ajax, name='visita_crear_ajax'),
]
