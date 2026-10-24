from django.urls import path
from .views import (
    monitoreo,
    detectar_rostros,
    video_feed,
    escanear_camaras_ajax,
    seleccionar_camara_ajax,
    asignar_camara_ajax,
    renombrar_camara_ajax,
    eliminar_camara_ajax
)

urlpatterns = [
    path('', monitoreo, name='monitoreo'),
    path('detectar/', detectar_rostros, name='detectar_rostros'),
    path('video_feed/', video_feed, name='video_feed'),
    path('camaras/escanear/', escanear_camaras_ajax, name='escanear_camaras'),
    path('camaras/asignar/', asignar_camara_ajax, name='asignar_camara'),
    path('camaras/renombrar/', renombrar_camara_ajax, name='renombrar_camara'),
    path('camaras/eliminar/', eliminar_camara_ajax, name='eliminar_camara'),
    path('camaras/seleccionar/', seleccionar_camara_ajax, name='seleccionar_camara'),
]
