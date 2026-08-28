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

@login_required
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

@login_required
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
                ('/media/secure/' + acceso.foto_validacion.name)
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
@login_required
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
        acceso.resuelto = True

        acceso.save()


        return JsonResponse({

            'success': True

        })

    return JsonResponse({

        'success': False

    })


@csrf_exempt
@login_required
def validar_huella_acceso(request):
    """
    Endpoint para validación biométrica dactilar 1:1 con SecuGen Hamster Plus.
    Compara el template en vivo contra el template registrado de la persona.
    """
    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        })

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    acceso_id = data.get('acceso_id') or data.get('id')
    template_vivo = data.get('template') or data.get('template_base64')
    calidad = data.get('calidad', 0)

    if not acceso_id:
        return JsonResponse({
            'success': False,
            'error': 'Falta el identificador del acceso'
        })

    if not template_vivo:
        return JsonResponse({
            'success': False,
            'error': 'No se recibió el template dactilar del lector SecuGen'
        })

    try:
        acceso = Acceso.objects.select_related('persona').get(id=acceso_id)
    except Acceso.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Acceso no encontrado'
        })

    if not acceso.persona:
        return JsonResponse({
            'success': False,
            'error': 'El acceso no tiene una persona identificada para realizar la comparación 1:1.'
        })

    huella_reg = getattr(acceso.persona, 'huella', None)
    if not huella_reg or not huella_reg.template:
        return JsonResponse({
            'success': False,
            'error': f'{acceso.persona.nombre} {acceso.persona.apellido} no tiene una huella registrada en el sistema.'
        })

    try:
        from usuarios.utils.secugen_driver import comparar_templates_nativo
        resultado_match = comparar_templates_nativo(huella_reg.template, template_vivo)
    except Exception:
        from usuarios.utils.biometria_dactilar import comparar_templates_huella
        resultado_match = comparar_templates_huella(
            huella_reg.template,
            template_vivo,
            umbral_coincidencia=70.0
        )

    if resultado_match['match']:
        acceso.resultado = 'APROBADO_MANUAL'
        acceso.resuelto = True
        acceso.save()


        return JsonResponse({
            'success': True,
            'match': True,
            'score': resultado_match['score'],
            'persona': f'{acceso.persona.nombre} {acceso.persona.apellido}',
            'estado': acceso.resultado,
            'mensaje': f"Huella validada correctamente ({resultado_match['score']}% coincidencia)."
        })
    else:
        return JsonResponse({
            'success': True,
            'match': False,
            'score': resultado_match['score'],
            'persona': f'{acceso.persona.nombre} {acceso.persona.apellido}',
            'mensaje': f"Huella NO coincide con el registro ({resultado_match['score']}% coincidencia). Posible suplantación."
        })


