from django.urls import path
from .views import monitoreo
from .views import detectar_rostros

urlpatterns = [

    path('',monitoreo,name='monitoreo'),
    path('detectar/',detectar_rostros,name='detectar_rostros'),

]