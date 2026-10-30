import csv
from datetime import timedelta
from django.shortcuts import render
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.http import JsonResponse, HttpResponse
from django.utils.timezone import now
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt

from usuarios.models import Acceso, Persona
from .models import VisitaExterna
from .ai_vestimenta import comparar_vestimentas, analizar_vestimenta_individual


# ========================================================
# VISTA PRINCIPAL: CONTROL INTEGRAL Y BALANCE DE ACCESOS
# ========================================================
@login_required
def accesos(request):
    periodo = request.GET.get('periodo', 'todo')
    nombre_filtro = request.GET.get('nombre', '').strip()
    resultado_filtro = request.GET.get('resultado', '').strip()
    busqueda = request.GET.get('buscar', '').strip()
    hoy = now().date()

    # 1. QUERY DE ACCESOS GENERALES
    queryset = Acceso.objects.select_related('persona').all()

    # Filtro por período
    if periodo == 'hoy':
        queryset = queryset.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    # Filtro específico por Nombre
    if nombre_filtro:
        queryset = queryset.filter(
            Q(persona__nombre__icontains=nombre_filtro) |
            Q(persona__apellido__icontains=nombre_filtro) |
            Q(nombre_detectado__icontains=nombre_filtro)
        )

    # Filtro específico por Resultado (Permitido, Denegado, Revisión)
    if resultado_filtro:
        if resultado_filtro == 'PERMITIDO':
            queryset = queryset.filter(resultado__in=['PERMITIDO', 'APROBADO_MANUAL'])
        elif resultado_filtro == 'DENEGADO':
            queryset = queryset.filter(resultado__in=['DENEGADO', 'RECHAZADO'])
        elif resultado_filtro == 'REVISION':
            queryset = queryset.filter(resultado='REVISION')
        else:
            queryset = queryset.filter(resultado__iexact=resultado_filtro)

    # Búsqueda general combinada
    if busqueda:
        queryset = queryset.filter(
            Q(persona__nombre__icontains=busqueda) |
            Q(persona__apellido__icontains=busqueda) |
            Q(persona__rut__icontains=busqueda) |
            Q(camara__icontains=busqueda) |
            Q(resultado__icontains=busqueda) |
            Q(nombre_detectado__icontains=busqueda)
        )

    queryset = queryset.order_by('-fecha_hora')

    # KPIs de Accesos Globales
    total = queryset.count()
    permitidos = queryset.filter(resultado__in=['PERMITIDO', 'APROBADO_MANUAL']).count()
    denegados = queryset.filter(resultado__in=['DENEGADO', 'RECHAZADO']).count()
    revision = queryset.filter(resultado='REVISION').count()

    # 2. SECCIÓN: CONTROL Y BALANCE DE AFORO DE PERSONAS EXTERNAS (VISITANTES)
    visitas_qs = VisitaExterna.objects.select_related('persona').all()
    if periodo == 'hoy':
        visitas_qs = visitas_qs.filter(fecha_ingreso__date=hoy)
    elif periodo in ['semana', '7']:
        visitas_qs = visitas_qs.filter(fecha_ingreso__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        visitas_qs = visitas_qs.filter(fecha_ingreso__date__gte=hoy - timedelta(days=30))

    if busqueda or nombre_filtro:
        termino = nombre_filtro or busqueda
        visitas_qs = visitas_qs.filter(
            Q(nombre_visitante__icontains=termino) |
            Q(rut_visitante__icontains=termino) |
            Q(pertenencias_declaradas__icontains=termino) |
            Q(interno_a_visitar__icontains=termino)
        )

    total_ingresos_ext = visitas_qs.count()
    total_egresos_ext = visitas_qs.filter(fecha_egreso__isnull=False).count()
    dentro_penal = max(0, total_ingresos_ext - total_egresos_ext)
    alertas_vestimenta_count = visitas_qs.filter(alerta_vestimenta=True).count()

    tasa_retorno = round((total_egresos_ext / total_ingresos_ext * 100), 1) if total_ingresos_ext > 0 else 100.0

    # Personas ingresadas (columna izquierda)
    visitas_ingresadas = visitas_qs.order_by('-fecha_ingreso')[:25]
    # Personas egresadas (columna derecha)
    visitas_egresadas = visitas_qs.filter(fecha_egreso__isnull=False).order_by('-fecha_egreso')[:25]

    # 3. PAGINACIÓN DE LA TABLA PRINCIPAL (Configurada a 7 elementos para no extender la página)
    paginator = Paginator(queryset, 7)
    page = request.GET.get('page')
    accesos_paginados = paginator.get_page(page)

    context = {
        'accesos': accesos_paginados,
        'total': total,
        'permitidos': permitidos,
        'denegados': denegados,
        'revision': revision,
        'periodo': periodo,
        'nombre_filtro': nombre_filtro,
        'resultado_filtro': resultado_filtro,
        # Balance y Visitas Externas
        'total_ingresos_ext': total_ingresos_ext,
        'total_egresos_ext': total_egresos_ext,
        'dentro_penal': dentro_penal,
        'alertas_vestimenta_count': alertas_vestimenta_count,
        'tasa_retorno': tasa_retorno,
        'visitas_ingresadas': visitas_ingresadas,
        'visitas_egresadas': visitas_egresadas,
    }

    return render(request, 'accesos/accesos.html', context)


# ========================================================
# ENDPOINT AJAX: TABLA GENERAL DE ACCESOS (CON FILTROS Y 7 ELEMENTOS)
# ========================================================
@login_required
def accesos_ajax(request):
    periodo = request.GET.get('periodo', 'todo')
    nombre_filtro = request.GET.get('nombre', '').strip()
    resultado_filtro = request.GET.get('resultado', '').strip()
    busqueda = request.GET.get('buscar', '').strip()
    hoy = now().date()

    accesos_qs = Acceso.objects.select_related('persona').all()

    if periodo == 'hoy':
        accesos_qs = accesos_qs.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        accesos_qs = accesos_qs.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        accesos_qs = accesos_qs.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    if nombre_filtro:
        accesos_qs = accesos_qs.filter(
            Q(persona__nombre__icontains=nombre_filtro) |
            Q(persona__apellido__icontains=nombre_filtro) |
            Q(nombre_detectado__icontains=nombre_filtro)
        )

    if resultado_filtro:
        if resultado_filtro == 'PERMITIDO':
            accesos_qs = accesos_qs.filter(resultado__in=['PERMITIDO', 'APROBADO_MANUAL'])
        elif resultado_filtro == 'DENEGADO':
            accesos_qs = accesos_qs.filter(resultado__in=['DENEGADO', 'RECHAZADO'])
        elif resultado_filtro == 'REVISION':
            accesos_qs = accesos_qs.filter(resultado='REVISION')
        else:
            accesos_qs = accesos_qs.filter(resultado__iexact=resultado_filtro)

    if busqueda:
        accesos_qs = accesos_qs.filter(
            Q(persona__nombre__icontains=busqueda) |
            Q(persona__apellido__icontains=busqueda) |
            Q(persona__rut__icontains=busqueda) |
            Q(camara__icontains=busqueda) |
            Q(resultado__icontains=busqueda) |
            Q(nombre_detectado__icontains=busqueda)
        )

    accesos_qs = accesos_qs.order_by('-fecha_hora')
    # Paginación compacta de 7 elementos
    paginator = Paginator(accesos_qs, 7)
    page = request.GET.get('page')
    accesos_pag = paginator.get_page(page)

    tabla_html = render_to_string('accesos/partials/tabla.html', {'accesos': accesos_pag})
    paginacion_html = render_to_string('accesos/partials/paginacion.html', {'accesos': accesos_pag})

    return JsonResponse({
        'tabla': tabla_html,
        'paginacion': paginacion_html,
        'total': accesos_qs.count()
    })


# ========================================================
# ENDPOINTS AJAX: DETALLES, VESTIMENTA Y GESTIÓN DE VISITAS
# ========================================================
@login_required
def visita_detalle_json(request, visita_id):
    """Retorna la ficha técnica de la persona externa, vestimenta y pertenencias en JSON."""
    try:
        visita = VisitaExterna.objects.select_related('persona').get(id=visita_id)
        
        foto_ingreso_url = visita.foto_ingreso.url if visita.foto_ingreso else (
            visita.persona.foto.url if visita.persona and visita.persona.foto else '/static/img/no-face.jpg'
        )
        foto_egreso_url = visita.foto_egreso.url if visita.foto_egreso else None

        data = {
            'id': visita.id,
            'nombre': visita.nombre_visitante,
            'rut': visita.rut_visitante or '---',
            'telefono': visita.telefono or '---',
            'interno': visita.interno_a_visitar or 'No especificado',
            'parentesco': visita.parentesco_o_motivo or 'Visita general',
            'fecha_ingreso': visita.fecha_ingreso.strftime('%d/%m/%Y %H:%M:%S'),
            'puerta_ingreso': visita.puerta_ingreso,
            'foto_ingreso_url': foto_ingreso_url,
            'prenda_superior': visita.prenda_superior or 'No especificada',
            'color_superior': visita.color_superior or '---',
            'prenda_inferior': visita.prenda_inferior or 'No especificada',
            'color_inferior': visita.color_inferior or '---',
            'calzado': visita.calzado or '---',
            'pertenencias': visita.pertenencias_declaradas or 'Sin pertenencias registradas',
            'descripcion_general': visita.descripcion_general or '',
            'ha_egresado': visita.ha_egresado,
            'fecha_egreso': visita.fecha_egreso.strftime('%d/%m/%Y %H:%M:%S') if visita.fecha_egreso else None,
            'puerta_egreso': visita.puerta_egreso or '',
            'foto_egreso_url': foto_egreso_url,
            'estado': visita.estado,
            'estado_display': visita.get_estado_display(),
            'similitud_vestimenta': visita.similitud_vestimenta,
            'coincidencia_superior': visita.coincidencia_superior,
            'coincidencia_inferior': visita.coincidencia_inferior,
            'alerta_vestimenta': visita.alerta_vestimenta,
            'dictamen_ia': visita.dictamen_ia or '',
            'observaciones_guardia': visita.observaciones_guardia or ''
        }
        return JsonResponse({'success': True, 'visita': data})
    except VisitaExterna.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Visita externa no encontrada'}, status=404)


@csrf_exempt
@login_required
def visita_guardar_pertenencias(request, visita_id):
    """Permite al guardia actualizar la descripción de vestimenta y pertenencias en vivo."""
    if request.method == 'POST':
        try:
            visita = VisitaExterna.objects.get(id=visita_id)
            visita.prenda_superior = request.POST.get('prenda_superior', visita.prenda_superior).strip()
            visita.color_superior = request.POST.get('color_superior', visita.color_superior).strip()
            visita.prenda_inferior = request.POST.get('prenda_inferior', visita.prenda_inferior).strip()
            visita.color_inferior = request.POST.get('color_inferior', visita.color_inferior).strip()
            visita.calzado = request.POST.get('calzado', visita.calzado).strip()
            visita.pertenencias_declaradas = request.POST.get('pertenencias', visita.pertenencias_declaradas).strip()
            visita.observaciones_guardia = request.POST.get('observaciones', visita.observaciones_guardia).strip()
            visita.save()
            return JsonResponse({'success': True, 'mensaje': 'Pertenencias y atuendo actualizados correctamente.'})
        except VisitaExterna.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Visita no encontrada'}, status=404)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@csrf_exempt
@login_required
def visita_analizar_ia(request, visita_id):
    """Ejecuta el peritaje de visión por computadora para comparar prendas o extraer colores."""
    try:
        visita = VisitaExterna.objects.get(id=visita_id)

        # Si cuenta con foto de entrada y salida, ejecuta el comparador dual
        if visita.foto_ingreso and visita.foto_egreso:
            res = comparar_vestimentas(visita.foto_ingreso, visita.foto_egreso)
            if res.get('exito'):
                visita.similitud_vestimenta = res['similitud_global']
                visita.coincidencia_superior = res['coincidencia_superior']
                visita.coincidencia_inferior = res['coincidencia_inferior']
                visita.alerta_vestimenta = res['alerta_vestimenta']
                visita.dictamen_ia = res['dictamen']
                visita.estado = 'ALERTA_DISCREPANCIA' if res['alerta_vestimenta'] else 'FINALIZADA'
                visita.save()
                return JsonResponse({'success': True, 'resultado': res})
            else:
                return JsonResponse({'success': False, 'error': res.get('dictamen', 'Error al procesar')})
        elif visita.foto_ingreso:
            res = analizar_vestimenta_individual(visita.foto_ingreso)
            if res.get('exito'):
                if not visita.color_superior or visita.color_superior == '---':
                    visita.color_superior = res['color_superior']
                if not visita.color_inferior or visita.color_inferior == '---':
                    visita.color_inferior = res['color_inferior']
                visita.dictamen_ia = res['resumen']
                visita.save()
                return JsonResponse({'success': True, 'resultado': res, 'tipo': 'individual'})

        return JsonResponse({'success': False, 'error': 'Se requiere al menos una fotografía de la persona para realizar el escaneo.'})
    except VisitaExterna.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Visita no encontrada'}, status=404)


@csrf_exempt
@login_required
def visita_registrar_egreso_ajax(request, visita_id):
    """Registra la salida de un visitante externo y ejecuta inmediatamente la auditoría IA de ropa."""
    if request.method == 'POST':
        try:
            visita = VisitaExterna.objects.get(id=visita_id)
            visita.fecha_egreso = timezone.now()
            visita.puerta_egreso = request.POST.get('puerta_egreso', 'Puesto de Control 1 [Egreso]')

            foto = request.FILES.get('foto_egreso')
            if foto:
                visita.foto_egreso = foto
                visita.save()

            if visita.foto_ingreso and visita.foto_egreso:
                res = comparar_vestimentas(visita.foto_ingreso, visita.foto_egreso)
                if res.get('exito'):
                    visita.similitud_vestimenta = res['similitud_global']
                    visita.coincidencia_superior = res['coincidencia_superior']
                    visita.coincidencia_inferior = res['coincidencia_inferior']
                    visita.alerta_vestimenta = res['alerta_vestimenta']
                    visita.dictamen_ia = res['dictamen']
                    visita.estado = 'ALERTA_DISCREPANCIA' if res['alerta_vestimenta'] else 'FINALIZADA'
            else:
                visita.estado = 'FINALIZADA'

            visita.save()
            return JsonResponse({
                'success': True,
                'mensaje': 'Egreso registrado exitosamente.',
                'estado': visita.estado,
                'similitud': visita.similitud_vestimenta,
                'alerta': visita.alerta_vestimenta
            })
        except VisitaExterna.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Visita no encontrada'}, status=404)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@csrf_exempt
@login_required
def visita_crear_ajax(request):
    """Crea un nuevo registro de visitante externo con pertenencias y foto opcional."""
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre_visitante', '').strip()
            if not nombre:
                return JsonResponse({'success': False, 'error': 'El nombre del visitante es obligatorio.'})

            rut = request.POST.get('rut_visitante', '').strip()
            interno = request.POST.get('interno_a_visitar', '').strip()
            parentesco = request.POST.get('parentesco_o_motivo', 'Visita general').strip()
            prenda_sup = request.POST.get('prenda_superior', '').strip()
            color_sup = request.POST.get('color_superior', '').strip()
            prenda_inf = request.POST.get('prenda_inferior', '').strip()
            color_inf = request.POST.get('color_inferior', '').strip()
            calzado = request.POST.get('calzado', '').strip()
            pertenencias = request.POST.get('pertenencias_declaradas', '').strip()
            observaciones = request.POST.get('observaciones_guardia', '').strip()

            visita = VisitaExterna.objects.create(
                nombre_visitante=nombre,
                rut_visitante=rut,
                interno_a_visitar=interno,
                parentesco_o_motivo=parentesco,
                prenda_superior=prenda_sup,
                color_superior=color_sup,
                prenda_inferior=prenda_inf,
                color_inferior=color_inf,
                calzado=calzado,
                pertenencias_declaradas=pertenencias,
                observaciones_guardia=observaciones,
                registrado_por=request.user if request.user.is_authenticated else None
            )

            foto = request.FILES.get('foto_ingreso')
            if foto:
                visita.foto_ingreso = foto
                visita.save()
                res = analizar_vestimenta_individual(visita.foto_ingreso)
                if res.get('exito'):
                    if not visita.color_superior:
                        visita.color_superior = res['color_superior']
                    if not visita.color_inferior:
                        visita.color_inferior = res['color_inferior']
                    visita.dictamen_ia = res['resumen']
                    visita.save()

            return JsonResponse({'success': True, 'mensaje': 'Visita externa registrada correctamente.', 'id': visita.id})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


# ========================================================
# EXPORTACIÓN CSV
# ========================================================
@login_required
def exportar_accesos_csv(request):
    periodo = request.GET.get('periodo', 'todo')
    nombre_filtro = request.GET.get('nombre', '').strip()
    resultado_filtro = request.GET.get('resultado', '').strip()
    busqueda = request.GET.get('buscar', '').strip()
    hoy = now().date()

    queryset = Acceso.objects.select_related('persona', 'resuelto_por').all()

    if periodo == 'hoy':
        queryset = queryset.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    if nombre_filtro:
        queryset = queryset.filter(
            Q(persona__nombre__icontains=nombre_filtro) |
            Q(persona__apellido__icontains=nombre_filtro) |
            Q(nombre_detectado__icontains=nombre_filtro)
        )

    if resultado_filtro:
        if resultado_filtro == 'PERMITIDO':
            queryset = queryset.filter(resultado__in=['PERMITIDO', 'APROBADO_MANUAL'])
        elif resultado_filtro == 'DENEGADO':
            queryset = queryset.filter(resultado__in=['DENEGADO', 'RECHAZADO'])
        elif resultado_filtro == 'REVISION':
            queryset = queryset.filter(resultado='REVISION')

    if busqueda:
        queryset = queryset.filter(
            Q(persona__nombre__icontains=busqueda) |
            Q(persona__apellido__icontains=busqueda) |
            Q(persona__rut__icontains=busqueda) |
            Q(camara__icontains=busqueda) |
            Q(resultado__icontains=busqueda)
        )

    queryset = queryset.order_by('-fecha_hora')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"reporte_accesos_{periodo}_{now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'ID Acceso', 'Fecha y Hora', 'Nombre y Apellido', 'RUT / Identificación',
        'Tipo de Usuario', 'Cámara / Canal', 'Resultado', 'Coincidencia IA (%)',
        'Estado de Resolución', 'Motivo de Resolución', 'Resuelto Por', 'Fecha de Resolución'
    ])

    for acc in queryset:
        if acc.persona:
            nombre = f"{acc.persona.nombre} {acc.persona.apellido}"
            rut = acc.persona.rut
            tipo = acc.persona.get_tipo_persona_display()
        else:
            nombre = acc.nombre_detectado or "Sujeto Desconocido"
            rut = "---"
            tipo = "Externo / Sin Registro"

        resuelto_str = "Resuelto" if acc.resuelto else "Pendiente"
        resuelto_por_str = (acc.resuelto_por.get_full_name() or acc.resuelto_por.username) if acc.resuelto_por else "---"
        fecha_res_str = acc.fecha_resolucion.strftime('%d/%m/%Y %H:%M:%S') if acc.fecha_resolucion else "---"

        writer.writerow([
            acc.id,
            acc.fecha_hora.strftime('%d/%m/%Y %H:%M:%S'),
            nombre, rut, tipo,
            acc.camara or 'Principal',
            acc.resultado,
            f"{acc.coincidencia:.1f}",
            resuelto_str,
            acc.motivo_resolucion or "---",
            resuelto_por_str,
            fecha_res_str
        ])

    return response
