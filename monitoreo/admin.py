from django.contrib import admin
from .models import ProtocoloLockdown


@admin.register(ProtocoloLockdown)
class ProtocoloLockdownAdmin(admin.ModelAdmin):
    list_display = ('id', 'activo', 'motivo', 'origen', 'fecha_activacion', 'fecha_desactivacion', 'activado_por')
    list_filter = ('activo', 'origen', 'fecha_activacion')
    search_fields = ('motivo', 'observaciones')
