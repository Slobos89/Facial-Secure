from django.urls import path
from .views import alertas, alertas_ajax
from . import views


urlpatterns = [
    path('',alertas,name='alertas'),
    path('ajax/',alertas_ajax,name='alertas_ajax'),
    path('resolver/<int:acceso_id>/',views.resolver_alerta,name='resolver_alerta'),
]