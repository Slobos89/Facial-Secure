from django.contrib import admin
from .models import Persona, Acceso, PerfilUsuario
from django.utils.html import format_html


admin.site.register(Persona)
admin.site.register(PerfilUsuario)

@admin.register(Acceso)
class AccesoAdmin(admin.ModelAdmin):

    list_display = (

        'preview_foto',

        'id',

        'nombre_detectado',

        'resultado',

        'coincidencia',

        'camara',

        'fecha_hora'

    )

    list_filter = (

        'resultado',

        'camara',

        'fecha_hora'

    )

    search_fields = (

        'nombre_detectado',

    )

    ordering = (

        '-fecha_hora',

    )


    def preview_foto(self, obj):

        if obj.foto_validacion:

            return format_html(

                '<img src="{}" width="70" style="border-radius:10px;">',

                obj.foto_validacion.url

            )

        return 'Sin foto'


    preview_foto.short_description = 'Foto'