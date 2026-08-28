from django.urls import path
from .views import validacion_biometrica
from . import views

urlpatterns = [

    path('', validacion_biometrica, name='validacion_biometrica'),
    path('kpis/', views.kpis_validacion, name='kpis_validacion'),
    path('cards/', views.cards_validacion, name='cards_validacion'),
    path('actualizar-estado/', views.actualizar_estado, name='actualizar_estado'),
    path('validar-huella/', views.validar_huella_acceso, name='validar_huella_acceso'),

]