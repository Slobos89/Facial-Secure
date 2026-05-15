from django.shortcuts import render
from usuarios.models import Acceso
from django.utils.timezone import now
from datetime import timedelta
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.template.loader import render_to_string

def alertas(request):

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
    # ALERTAS CRÍTICAS
    # =====================

    alertas_criticas = queryset.filter(

        resultado='DENEGADO',

    ).order_by('-fecha_hora')


    # =====================
    # ALERTAS REVISIÓN
    # =====================

    alertas_revision = queryset.filter(

        resultado='REVISION',

    ).order_by('-fecha_hora')


    # =====================
    # ALERTAS ACTIVAS
    # =====================

    alertas_activas = queryset.filter(

        resultado__in=[
            'DENEGADO',
            'REVISION'
        ],

    ).order_by('-fecha_hora')

    total_alertas = alertas_activas.count()

    paginator = Paginator(
        alertas_activas,
        5
    )

    page = request.GET.get(
        'page'
    )

    alertas_activas = paginator.get_page(
        page
    )

    # =====================
    # RESUELTOS
    # =====================

    resueltos = queryset.filter(

        resultado='PERMITIDO',

    ).count()


    # =====================
    # TIMELINE
    # =====================

    timeline = queryset.order_by(
        '-fecha_hora'
    )[:8]


    # =====================
    # KPIs
    # =====================


    total_criticas = alertas_criticas.count()

    total_revision = alertas_revision.count()


    return render(

        request,

        'alertas/alertas.html',

        {

            'alertas_activas': alertas_activas,
            'alertas_criticas': alertas_criticas,
            'alertas_revision': alertas_revision,
            'timeline': timeline,
            'total_alertas': total_alertas,
            'total_criticas': total_criticas,
            'total_revision': total_revision,
            'resueltos': resueltos,
            'periodo': periodo,

        }

    )

def alertas_ajax(request):

    periodo = request.GET.get(
        'periodo',
        'hoy'
    )

    hoy = now().date()

    queryset = Acceso.objects.all()


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


    alertas_activas = queryset.filter(

        resultado__in=[
            'DENEGADO',
            'REVISION'
        ]

    ).order_by('-fecha_hora')


    paginator = Paginator(
        alertas_activas,
        5
    )

    page = request.GET.get(
        'page'
    )

    alertas_activas = paginator.get_page(
        page
    )


    alerts_html = render_to_string(

        'alertas/partials/alerts.html',

        {

            'alertas_activas':
                alertas_activas

        }

    )


    pagination_html = render_to_string(

        'alertas/partials/pagination.html',

        {

            'alertas_activas':
                alertas_activas,

            'periodo':
                periodo

        }

    )


    return JsonResponse({

        'alerts':
            alerts_html,

        'pagination':
            pagination_html

    })