from django.shortcuts import render
from usuarios.models import Acceso
from django.utils.timezone import now
from datetime import timedelta
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

@login_required
def alertas(request):
    periodo = request.GET.get('periodo', 'todo')
    hoy = now().date()

    queryset = Acceso.objects.select_related('persona').all()

    if periodo == 'hoy':
        queryset = queryset.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    alertas_criticas = queryset.filter(resultado='DENEGADO').order_by('-fecha_hora')
    alertas_revision = queryset.filter(resultado='REVISION').order_by('-fecha_hora')
    alertas_activas_qs = queryset.filter(
        resultado__in=['DENEGADO', 'REVISION', 'RECHAZADO'],
        resuelto=False
    ).order_by('-fecha_hora')

    total_alertas = alertas_activas_qs.count()
    paginator = Paginator(alertas_activas_qs, 5)
    page = request.GET.get('page', 1)
    alertas_activas = paginator.get_page(page)

    for acceso in alertas_activas:
        acceso.preview_registrado = ''
        if acceso.persona and acceso.persona.foto:
            acceso.preview_registrado = '/media/secure/' + acceso.persona.foto.name

    total_criticas = alertas_criticas.count()
    total_revision = queryset.filter(resuelto=True).count()

    return render(
        request,
        'alertas/alertas.html',
        {
            'alertas_activas': alertas_activas,
            'alertas_criticas': alertas_criticas,
            'alertas_revision': alertas_revision,
            'total_alertas': total_alertas,
            'total_criticas': total_criticas,
            'total_revision': total_revision,
            'periodo': periodo,
        }
    )


@login_required
def alertas_ajax(request):
    periodo = request.GET.get('periodo', 'todo')
    hoy = now().date()

    queryset = Acceso.objects.select_related('persona').all()

    if periodo == 'hoy':
        queryset = queryset.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    alertas_activas_qs = queryset.filter(
        resultado__in=['DENEGADO', 'REVISION', 'RECHAZADO'],
        resuelto=False
    ).order_by('-fecha_hora')

    paginator = Paginator(alertas_activas_qs, 5)
    page = request.GET.get('page', 1)
    alertas_activas = paginator.get_page(page)

    for acceso in alertas_activas:
        acceso.preview_registrado = ''
        if acceso.persona and acceso.persona.foto:
            acceso.preview_registrado = '/media/secure/' + acceso.persona.foto.name

    alerts_html = render_to_string(
        'alertas/partials/alerts.html',
        {
            'alertas_activas': alertas_activas,
        }
    )

    pagination_html = render_to_string(
        'alertas/partials/pagination.html',
        {
            'alertas_activas': alertas_activas,
            'periodo': periodo,
        }
    )

    return JsonResponse({
        'alerts': alerts_html,
        'pagination': pagination_html,
    })


@require_POST
@login_required
def resolver_alerta(request, acceso_id):
    try:
        acceso = Acceso.objects.get(id=acceso_id)

        motivo = request.POST.get('motivo')
        accion = request.POST.get('accion')
        notas = request.POST.get('notas', '').strip()

        if not motivo and request.body:
            try:
                import json
                data = json.loads(request.body)
                motivo = data.get('motivo')
                accion = data.get('accion')
                notas = data.get('notas', '').strip()
            except Exception:
                pass

        if notas and motivo:
            motivo_final = f"{motivo} - Obs: {notas}"
        elif motivo:
            motivo_final = motivo
        else:
            motivo_final = "Incidente verificado y resuelto por operador de guardia"

        acceso.resuelto = True
        acceso.motivo_resolucion = motivo_final
        acceso.resuelto_por = request.user
        acceso.fecha_resolucion = now()

        if accion in ['APROBADO_MANUAL', 'RECHAZADO', 'PERMITIDO', 'DENEGADO']:
            acceso.resultado = accion

        acceso.save()

        return JsonResponse({
            'success': True,
            'mensaje': 'Alerta resuelta y registrada en bitácora'
        })
    except Acceso.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Alerta no encontrada'
        })


@login_required
def exportar_alertas_csv(request):
    import csv
    from django.http import HttpResponse

    periodo = request.GET.get('periodo', 'todo')
    hoy = now().date()

    queryset = Acceso.objects.filter(resultado__in=['DENEGADO', 'REVISION', 'RECHAZADO']).select_related('persona', 'resuelto_por')

    if periodo == 'hoy':
        queryset = queryset.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    queryset = queryset.order_by('-fecha_hora')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"bitacora_alertas_{periodo}_{now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'ID Incidente',
        'Fecha y Hora Detección',
        'Sujeto / Persona',
        'RUT / ID',
        'Tipo de Usuario',
        'Cámara',
        'Nivel de Riesgo',
        'Coincidencia IA (%)',
        'Estado',
        'Resuelto Por (Gendarme)',
        'Motivo / Justificación',
        'Fecha de Resolución'
    ])

    for acc in queryset:
        if acc.persona:
            nombre = f"{acc.persona.nombre} {acc.persona.apellido}"
            rut = acc.persona.rut
            tipo = acc.persona.get_tipo_persona_display()
        else:
            nombre = acc.nombre_detectado or "Sujeto Desconocido"
            rut = "---"
            tipo = "Externo / No identificado"

        riesgo = "ALTO" if acc.resultado in ['DENEGADO', 'RECHAZADO'] else "MEDIO"
        resuelto_por_str = (acc.resuelto_por.get_full_name() or acc.resuelto_por.username) if acc.resuelto_por else "Pendiente de revisión"
        fecha_res_str = acc.fecha_resolucion.strftime('%d/%m/%Y %H:%M:%S') if acc.fecha_resolucion else "---"

        writer.writerow([
            acc.id,
            acc.fecha_hora.strftime('%d/%m/%Y %H:%M:%S'),
            nombre,
            rut,
            tipo,
            acc.camara or 'Principal',
            riesgo,
            f"{acc.coincidencia:.1f}",
            "RESUELTO" if acc.resuelto else "ACTIVO",
            resuelto_por_str,
            acc.motivo_resolucion or "---",
            fecha_res_str
        ])

    return response
