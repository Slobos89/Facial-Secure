import json
from datetime import timedelta
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from usuarios.models import Acceso
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required


def _construir_filtro_fecha(periodo):
    """Construye el diccionario de filtro por fecha igual que en el Dashboard (por defecto 'hoy')."""
    ahora = timezone.now()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    if periodo == 'hoy':
        return {'fecha_hora__gte': min(inicio_dia, ahora - timedelta(hours=24))}
    elif periodo == '7':
        return {'fecha_hora__gte': ahora - timedelta(days=7)}
    elif periodo == '30':
        return {'fecha_hora__gte': ahora - timedelta(days=30)}
    elif periodo == 'todo':
        return {}
    return {'fecha_hora__gte': min(inicio_dia, ahora - timedelta(hours=24))}


@login_required
def validacion_biometrica(request):
    periodo = request.GET.get('periodo', 'hoy')
    filtro_fecha = _construir_filtro_fecha(periodo)

    accesos = Acceso.objects.filter(
        resultado='REVISION',
        **filtro_fecha
    ).select_related(
        'persona'
    ).order_by('-fecha_hora')

    pendientes = Acceso.objects.filter(
        resultado='REVISION',
        **filtro_fecha
    ).count()

    aprobados = Acceso.objects.filter(
        resultado='APROBADO_MANUAL',
        **filtro_fecha
    ).count()

    rechazados = Acceso.objects.filter(
        resultado='RECHAZADO',
        **filtro_fecha
    ).count()

    context = {
        'accesos': accesos,
        'pendientes': pendientes,
        'aprobados': aprobados,
        'rechazados': rechazados,
        'periodo': periodo,
    }

    return render(
        request,
        'validacion/validacion.html',
        context
    )


@login_required
def kpis_validacion(request):
    periodo = request.GET.get('periodo', 'hoy')
    filtro_fecha = _construir_filtro_fecha(periodo)

    pendientes = Acceso.objects.filter(
        resultado='REVISION',
        **filtro_fecha
    ).count()

    aprobados = Acceso.objects.filter(
        resultado='APROBADO_MANUAL',
        **filtro_fecha
    ).count()

    rechazados = Acceso.objects.filter(
        resultado='RECHAZADO',
        **filtro_fecha
    ).count()

    return JsonResponse({
        'pendientes': pendientes,
        'aprobados': aprobados,
        'rechazados': rechazados
    })


@login_required
def cards_validacion(request):
    periodo = request.GET.get('periodo', 'hoy')
    filtro_fecha = _construir_filtro_fecha(periodo)

    accesos = Acceso.objects.filter(
        resultado='REVISION',
        **filtro_fecha
    ).select_related(
        'persona'
    ).order_by(
        '-fecha_hora'
    )[:15]

    data = []
    for acceso in accesos:
        foto_en_vivo = ('/media/secure/' + acceso.foto_validacion.name) if acceso.foto_validacion else '/static/img/no-face.jpg'
        foto_registrada = ('/media/secure/' + acceso.persona.foto.name) if (acceso.persona and acceso.persona.foto) else '/static/img/no-face.jpg'

        data.append({
            'id': acceso.id,
            'nombre': acceso.persona.nombre + ' ' + acceso.persona.apellido if acceso.persona else (acceso.nombre_detectado or 'Sujeto No Identificado'),
            'rut': acceso.persona.rut if acceso.persona else '---',
            'coincidencia': round(acceso.coincidencia, 1),
            'camara': acceso.camara or 'Cámara Principal',
            'hora': acceso.fecha_hora.strftime('%H:%M:%S'),
            'fecha': acceso.fecha_hora.strftime('%d/%m/%Y'),
            'resultado': acceso.resultado,
            'foto': foto_en_vivo,
            'foto_registrada': foto_registrada,
            'tipo_persona': acceso.persona.get_tipo_persona_display() if acceso.persona else 'No identificado',
            'tiene_huella': bool(acceso.persona.huellas.exists()) if (acceso.persona and hasattr(acceso.persona, 'huellas')) else False
        })

    return JsonResponse({
        'cards': data
    })


@csrf_exempt
@login_required
def actualizar_estado(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        acceso_id = data.get('id')
        estado = data.get('estado')

        acceso = Acceso.objects.select_related('persona').get(id=acceso_id)
        acceso.resultado = estado
        acceso.resuelto = True
        if request.user.is_authenticated:
            acceso.resuelto_por = request.user
        acceso.fecha_resolucion = timezone.now()
        acceso.save()

        if estado in ['PERMITIDO', 'APROBADO_MANUAL']:
            from accesos.models import sincronizar_visita_externa_desde_acceso
            sincronizar_visita_externa_desde_acceso(acceso, usuario=request.user)

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
        if request.user.is_authenticated:
            acceso.resuelto_por = request.user
        acceso.fecha_resolucion = timezone.now()
        acceso.save()

        from accesos.models import sincronizar_visita_externa_desde_acceso
        sincronizar_visita_externa_desde_acceso(acceso, usuario=request.user)

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
