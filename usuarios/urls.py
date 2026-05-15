from django.urls import path
from django.http import JsonResponse
from django.template.loader import render_to_string
from .views import usuarios, crear_persona, validar_rostro,historial_ajax, live_feed

urlpatterns = [
    path('', usuarios, name='usuarios'),
    path('nuevo/', crear_persona, name='crear_persona'),
    path('validar/',validar_rostro,name='validar_rostro'),
    path('historial-ajax/',historial_ajax,name='historial_ajax'),
    path('live-feed/',live_feed,name='live_feed'),
]