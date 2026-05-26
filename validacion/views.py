import json
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from usuarios.models import Acceso
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def validacion_biometrica(request):

    accesos = Acceso.objects.filter(
        resultado='REVISION'
    ).select_related(
        'persona'
    ).order_by('-fecha_hora')

    hoy = timezone.now().date()

    pendientes = Acceso.objects.filter(
        resultado='REVISION',
        fecha_hora__date=hoy
    ).count()

    aprobados = Acceso.objects.filter(
        resultado='APROBADO_MANUAL',
        fecha_hora__date=hoy
    ).count()

    rechazados = Acceso.objects.filter(
        resultado='RECHAZADO',
        fecha_hora__date=hoy
    ).count()

    context = {

        'accesos': accesos,

        'pendientes': pendientes,

        'aprobados': aprobados,

        'rechazados': rechazados

    }

    return render(

        request,

        'validacion/validacion.html',

        context

    )

def kpis_validacion(request):

    hoy = timezone.now().date()

    pendientes = Acceso.objects.filter(
        resultado='REVISION',
        fecha_hora__date=hoy
    ).count()

    aprobados = Acceso.objects.filter(
        resultado='APROBADO_MANUAL',
        fecha_hora__date=hoy
    ).count()

    rechazados = Acceso.objects.filter(
        resultado='RECHAZADO',
        fecha_hora__date=hoy
    ).count()

    return JsonResponse({

        'pendientes': pendientes,

        'aprobados': aprobados,

        'rechazados': rechazados

    })

def cards_validacion(request):

    accesos = Acceso.objects.filter(
        resultado='REVISION'
    ).select_related(
        'persona'
    ).order_by(
        '-fecha_hora'
    )[:10]

    data = []

    for acceso in accesos:

        data.append({

            'id': acceso.id,

            'nombre':
                acceso.nombre_detectado,

            'coincidencia':
                acceso.coincidencia,

            'camara':
                acceso.camara,

            'hora':
                acceso.fecha_hora.strftime(
                    '%H:%M:%S'
                ),

            'resultado':
                acceso.resultado,

            'foto':
                acceso.foto_validacion.url
                if acceso.foto_validacion
                else '/static/img/no-face.jpg',

            'tipo_persona':
                acceso.persona.tipo_persona
                if acceso.persona
                else 'No identificado'

        })

    return JsonResponse({

        'cards': data

    })

@csrf_exempt
def actualizar_estado(request):

    if request.method == 'POST':

        data = json.loads(
            request.body
        )

        acceso_id = data.get('id')

        estado = data.get('estado')


        acceso = Acceso.objects.get(
            id=acceso_id
        )

        acceso.resultado = estado

        acceso.save()


        return JsonResponse({

            'success': True

        })

    return JsonResponse({

        'success': False

    })

