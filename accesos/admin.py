from django.contrib import admin
from .models import VisitaExterna


@admin.register(VisitaExterna)
class VisitaExternaAdmin(admin.ModelAdmin):
    list_display = ('nombre_visitante', 'rut_visitante', 'interno_a_visitar', 'modulo_interno', 'nivel_riesgo_inteligencia', 'fecha_ingreso', 'fecha_egreso', 'estado', 'similitud_vestimenta', 'alerta_vestimenta')
    list_filter = ('estado', 'nivel_riesgo_inteligencia', 'alerta_vestimenta', 'modulo_interno', 'fecha_ingreso')
    search_fields = ('nombre_visitante', 'rut_visitante', 'pertenencias_declaradas', 'interno_a_visitar')
    readonly_fields = ('similitud_vestimenta', 'coincidencia_superior', 'coincidencia_inferior', 'dictamen_ia')
