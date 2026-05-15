from django.urls import path
from .views import dashboard, dashboard_data,exportar_pdf

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('dashboard/data/',dashboard_data,name='dashboard_data'),
    path('exportar-pdf/',exportar_pdf,name='exportar_pdf'),
]