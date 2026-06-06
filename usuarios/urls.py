from django.urls import path
from django.http import JsonResponse
from django.template.loader import render_to_string
from .views import usuarios, crear_persona, validar_rostro,historial_ajax, live_feed, entrenar_ia
from . import views

urlpatterns = [
    path('', usuarios, name='usuarios'),
    path('nuevo/', crear_persona, name='crear_persona'),
    path('validar/',validar_rostro,name='validar_rostro'),
    path('historial-ajax/',historial_ajax,name='historial_ajax'),
    path('live-feed/',live_feed,name='live_feed'),
    path('entrenar-ia/',entrenar_ia,name='entrenar_ia'),
    path('editar-usuario/<int:persona_id>/',views.editar_usuario,name='editar_usuario'),
    path('reenrolar-rostro/<int:persona_id>/',views.reenrolar_rostro,name='reenrolar_rostro'),
    path('registrar-huella/<int:persona_id>/',views.registrar_huella,name='registrar_huella'),
]