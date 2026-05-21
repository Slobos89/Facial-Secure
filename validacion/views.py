from django.shortcuts import render
from usuarios.models import Acceso
from django.core.paginator import Paginator

def validacion_biometrica(request):

    accesos = Acceso.objects.filter(
        resultado='REVISION'
    ).select_related(
        'persona'
    ).order_by('-fecha_hora')

    pendientes = accesos.count()

    aprobados = Acceso.objects.filter(
        resultado='APROBADO_MANUAL'
    ).count()

    rechazados = Acceso.objects.filter(
        resultado='RECHAZADO'
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