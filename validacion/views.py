from django.shortcuts import render
from usuarios.models import Acceso
from django.core.paginator import Paginator

def validacion_biometrica(request):

    accesos_lista = Acceso.objects.all().order_by(
        '-fecha_hora'
    )

    paginator = Paginator(
        accesos_lista,
        10
    )

    page_number = request.GET.get('page')

    accesos = paginator.get_page(
        page_number
    )

    contexto = {

        'persona_detectada': None,

        'coincidencia': None,

        'estado': 'Esperando validación',

        'accesos': accesos
    }

    return render(
        request,
        'validacion/validacion.html',
        contexto
    )