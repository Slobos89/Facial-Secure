from django.urls import path
from .views import accesos, accesos_ajax


urlpatterns = [
    path('',accesos,name='accesos'),
    path('ajax/',accesos_ajax,name='accesos_ajax'),
]