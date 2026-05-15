from django.urls import path
from .views import validacion_biometrica

urlpatterns = [

    path('',validacion_biometrica,name='validacion_biometrica'),

]