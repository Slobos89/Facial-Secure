from django.shortcuts import render
from django.core.paginator import Paginator
from usuarios.models import Acceso
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Q
from django.contrib.auth.decorators import login_required

# =========================
# MÓDULO ACCESOS
# =========================
@login_required
def accesos(request):

    periodo = request.GET.get(
        'periodo',
        'todo'
    )

    hoy = now().date()

    # =====================
    # QUERY BASE
    # =====================
    queryset = Acceso.objects.select_related('persona').all()

    # =====================
    # FILTROS POR PERIODO
    # =====================
    if periodo == 'hoy':
        queryset = queryset.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        queryset = queryset.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass


    # =====================
    # FILTRO BÚSQUEDA
    # =====================

    busqueda = request.GET.get(
        'buscar'
    )

    if busqueda:

        queryset = queryset.filter(

            Q(
                persona__nombre__icontains=
                busqueda
            )

            |

            Q(
                persona__apellido__icontains=
                busqueda
            )

            |

            Q(
                persona__rut__icontains=
                busqueda
            )

            |

            Q(
                camara__icontains=
                busqueda
            )

            |

            Q(
                resultado__icontains=
                busqueda
            )


        )


    # =====================
    # ORDER BY
    # =====================

    queryset = queryset.order_by(
        '-fecha_hora'
    )


    # =====================
    # KPIs
    # =====================

    total = queryset.count()

    permitidos = queryset.filter(
        resultado__in=[
            'PERMITIDO',
            'APROBADO_MANUAL'
        ]
    ).count()

    denegados = queryset.filter(
        resultado__in=[
            'DENEGADO',
            'RECHAZADO'
        ]
    ).count()

    revision = queryset.filter(
        resultado='REVISION'
    ).count()


    # =====================
    # PAGINACIÓN
    # =====================

    paginator = Paginator(
        queryset,
        15
    )

    page = request.GET.get(
        'page'
    )

    accesos = paginator.get_page(page)


    # =====================
    # RENDER
    # =====================

    return render(

        request,

        'accesos/accesos.html',

        {

            'accesos': accesos,

            'total': total,

            'permitidos': permitidos,

            'denegados': denegados,

            'revision': revision,

            'periodo': periodo,

        }

    )

@login_required
def accesos_ajax(request):
    periodo = request.GET.get('periodo', 'todo')
    hoy = now().date()

    accesos = Acceso.objects.select_related('persona').all()

    if periodo == 'hoy':
        accesos = accesos.filter(fecha_hora__date=hoy)
    elif periodo in ['semana', '7']:
        accesos = accesos.filter(fecha_hora__date__gte=hoy - timedelta(days=7))
    elif periodo in ['mes', '30']:
        accesos = accesos.filter(fecha_hora__date__gte=hoy - timedelta(days=30))
    elif periodo == 'todo':
        pass

    accesos = accesos.order_by('-fecha_hora')

    busqueda = request.GET.get(
        'buscar'
    )

    if busqueda:

        accesos = accesos.filter(

            Q(
                persona__nombre__icontains=
                busqueda
            )

            |

            Q(
                persona__apellido__icontains=
                busqueda
            )

            |

            Q(
                persona__rut__icontains=
                busqueda
            )

            |

            Q(
                camara__icontains=
                busqueda
            )

            |

            Q(
                resultado__icontains=
                busqueda
            )


        )


    paginator = Paginator(
        accesos,
        15
    )

    page = request.GET.get(
        'page'
    )

    accesos = paginator.get_page(page)


    tabla_html = render_to_string(

        'accesos/partials/tabla.html',

        {
            'accesos': accesos
        }

    )

    paginacion_html = render_to_string(

        'accesos/partials/paginacion.html',

        {
            'accesos': accesos
        }

    )

    return JsonResponse({

        'tabla': tabla_html,

        'paginacion': paginacion_html

    })


@login_required
def exportar_accesos_csv(request):
    import csv
    from django.http import HttpResponse

    periodo = request.GET.get('periodo', 'todo')
    busqueda = request.GET.get('buscar', '').strip()
    resultado_filtro = request.GET.get('resultado', '').strip()
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

    if resultado_filtro:
        queryset = queryset.filter(resultado=resultado_filtro)

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

    # Byte Order Mark UTF-8 para compatibilidad directa con Microsoft Excel en Windows
    response.write('\ufeff')

    writer = csv.writer(response, delimiter=';')
    writer.writerow([
        'ID Acceso',
        'Fecha y Hora',
        'Nombre y Apellido',
        'RUT / Identificación',
        'Tipo de Usuario',
        'Cámara / Canal',
        'Resultado',
        'Coincidencia IA (%)',
        'Estado de Resolución',
        'Motivo de Resolución',
        'Resuelto Por',
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
            tipo = "Externo / Sin Registro"

        resuelto_str = "Resuelto" if acc.resuelto else "Pendiente"
        resuelto_por_str = (acc.resuelto_por.get_full_name() or acc.resuelto_por.username) if acc.resuelto_por else "---"
        fecha_res_str = acc.fecha_resolucion.strftime('%d/%m/%Y %H:%M:%S') if acc.fecha_resolucion else "---"

        writer.writerow([
            acc.id,
            acc.fecha_hora.strftime('%d/%m/%Y %H:%M:%S'),
            nombre,
            rut,
            tipo,
            acc.camara or 'Principal',
            acc.resultado,
            f"{acc.coincidencia:.1f}",
            resuelto_str,
            acc.motivo_resolucion or "---",
            resuelto_por_str,
            fecha_res_str
        ])

    return response