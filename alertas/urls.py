from django.urls import path
from .views import alertas, alertas_ajax


urlpatterns = [
    path('',alertas,name='alertas'),
    path('ajax/',alertas_ajax,name='alertas_ajax'),
]