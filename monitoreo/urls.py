from django.urls import path
from .views import (
    monitoreo,
    detectar_rostros,
    ultimas_detecciones_ajax,
    video_feed,
    escanear_camaras_ajax,
    probar_conexion_camara_ajax,
    seleccionar_camara_ajax,
    asignar_camara_ajax,
    renombrar_camara_ajax,
    eliminar_camara_ajax
)

urlpatterns = [
    path('', monitoreo, name='monitoreo'),
    path('detectar/', detectar_rostros, name='detectar_rostros'),
    path('ultimas_detecciones/', ultimas_detecciones_ajax, name='ultimas_detecciones'),
    path('video_feed/', video_feed, name='video_feed'),
    path('camaras/escanear/', escanear_camaras_ajax, name='escanear_camaras'),
    path('camaras/probar/', probar_conexion_camara_ajax, name='probar_camara'),
    path('camaras/asignar/', asignar_camara_ajax, name='asignar_camara'),
    path('camaras/renombrar/', renombrar_camara_ajax, name='renombrar_camara'),
    path('camaras/eliminar/', eliminar_camara_ajax, name='eliminar_camara'),
    path('camaras/seleccionar/', seleccionar_camara_ajax, name='seleccionar_camara'),
]
