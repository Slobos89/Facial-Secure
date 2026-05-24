from django.shortcuts import render
from django.core.paginator import Paginator
from usuarios.models import Acceso
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Q

# =========================
# MÓDULO ACCESOS
# =========================

def accesos(request):

    periodo = request.GET.get(
        'periodo',
        'hoy'
    )

    hoy = now().date()


    # =====================
    # QUERY BASE
    # =====================

    queryset = Acceso.objects.all()


    # =====================
    # FILTROS POR PERIODO
    # =====================

    if periodo == 'hoy':

        queryset = queryset.filter(
            fecha_hora__date=hoy
        )


    elif periodo == 'semana':

        queryset = queryset.filter(

            fecha_hora__date__gte=
            hoy - timedelta(days=7)

        )


    elif periodo == 'mes':

        queryset = queryset.filter(

            fecha_hora__month=hoy.month,

            fecha_hora__year=hoy.year

        )


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

def accesos_ajax(request):

    accesos = Acceso.objects.order_by(
        '-fecha_hora'
    )

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