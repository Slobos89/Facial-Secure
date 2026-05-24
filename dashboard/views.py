from django.shortcuts import render
from django.db.models import Avg
from django.utils.timezone import now
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db.models.functions import ExtractHour
from django.db.models import Count
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
import json
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from usuarios.models import Persona, Acceso



def dashboard(request):
    hoy = now()
    fecha_inicio = hoy.date()
    ayer = (hoy - timedelta(days=1)).date()
    horas = []
    totales = []

    periodo = request.GET.get(
        'periodo',
        'hoy'
    )

    if periodo == '7':

        fecha_inicio = (
            hoy - timedelta(days=7)
        ).date()


    elif periodo == '30':

        fecha_inicio = (
            hoy - timedelta(days=30)
        ).date()

    total_personas = Persona.objects.count()

    internos = Persona.objects.filter(
        tipo_persona='interno'
    ).count()

    gendarmes = Persona.objects.filter(
        tipo_persona='gendarme'
    ).count()

    externos = Persona.objects.filter(
        tipo_persona='externo'
    ).count()

    accesos_hoy = Acceso.objects.filter(
        fecha_hora__date__gte=fecha_inicio
    ).count()

    permitidos = Acceso.objects.filter(
        resultado__in=[ 'PERMITIDO',
                        'APROBADO_MANUAL'
        ],
        fecha_hora__date__gte=fecha_inicio
    ).count()

    permitidos_ayer = Acceso.objects.filter(
        resultado__in=[ 'PERMITIDO',
                        'APROBADO_MANUAL'
        ],
        fecha_hora__date=ayer
    ).count()

    if permitidos_ayer > 0:
        porcentaje_cambio = round(
            (
                (permitidos - permitidos_ayer)
                / permitidos_ayer
            ) * 100,
            1
        )
    else:
        porcentaje_cambio = 0

    denegados = Acceso.objects.filter(
        resultado__in=[
            'DENEGADO',
            'RECHAZADO'
        ],
        fecha_hora__date__gte=fecha_inicio
    ).count()

    alerta_texto = None

    alerta_tipo = None


    if denegados >= 10:

        alerta_texto = (
            'Alta cantidad de accesos denegados'
        )

        alerta_tipo = 'critica'


    elif denegados >= 5:

        alerta_texto = (
            'Incremento de intentos fallidos'
        )

        alerta_tipo = 'advertencia'

    revision = Acceso.objects.filter(
        resultado='REVISION',
        fecha_hora__date__gte=fecha_inicio
    ).count()

    detecciones_live = Acceso.objects.filter(
        fecha_hora__gte=timezone.now() - timedelta(minutes=1)
    ).count()

    promedio = Acceso.objects.filter(
        coincidencia__gt=0
    ).aggregate(
        Avg('coincidencia')
    )['coincidencia__avg']

    recientes = Acceso.objects.order_by(
        '-fecha_hora'
    )[:10]

    eventos = Acceso.objects.order_by(
        '-fecha_hora'
    )[:10]

    accesos_por_hora = (

        Acceso.objects.filter(
            fecha_hora__date__gte=fecha_inicio
        )

        .annotate(
            hora=ExtractHour('fecha_hora')
        )

        .values('hora')

        .annotate(
            total=Count('id')
        )

        .order_by('hora')

    )

    for item in accesos_por_hora:

        horas.append(
            f"{item['hora']}:00"
        )

        totales.append(
            item['total']
        )

    

    contexto={
            'total_personas': total_personas,
            'internos': internos,
            'gendarmes': gendarmes,
            'externos': externos,
            'accesos_hoy': accesos_hoy,
            'permitidos': permitidos,
            'denegados': denegados,
            'revision': revision,
            'detecciones_live': detecciones_live,
            'promedio': round(promedio or 0, 2),
            'recientes': recientes,
            'porcentaje_cambio': porcentaje_cambio,
            'eventos': eventos,
            'horas': json.dumps(horas),
            'totales': json.dumps(totales),
            'estados_chart': json.dumps([
                permitidos,
                denegados,
                revision
            ]),
            'periodo': periodo,
            'alerta_texto': alerta_texto,
            'alerta_tipo': alerta_tipo,
    }

    return render(
        request,
        'dashboard/dashboard.html',
        contexto
    )

def dashboard_data(request):

    hoy = now().date()

    permitidos = Acceso.objects.filter(
        resultado__in=[ 'PERMITIDO',
                        'APROBADO_MANUAL'
        ],
        fecha_hora__date=hoy
    ).count()

    denegados = Acceso.objects.filter(
        resultado__in=[
            'DENEGADO',
            'RECHAZADO'
        ],
        fecha_hora__date=hoy
    ).count()

    revision = Acceso.objects.filter(
        resultado='REVISION'
    ).count()

    detecciones_live = Acceso.objects.filter(
        fecha_hora__gte=timezone.now() - timedelta(minutes=1)
    ).count()

    promedio = Acceso.objects.filter(
        fecha_hora__date=hoy,
        coincidencia__gt=0
    ).aggregate(
        Avg('coincidencia')
    )['coincidencia__avg']

    recientes = Acceso.objects.order_by(
        '-fecha_hora'
    )[:10]

    eventos = []

    for acceso in recientes:

        eventos.append({

            'persona':
                acceso.persona.nombre
                if acceso.persona
                else 'Desconocido',

            'resultado':
                acceso.resultado,

            'coincidencia':
                acceso.coincidencia,

            'hora':
                acceso.fecha_hora.strftime('%H:%M')

        })

    return JsonResponse({

        'permitidos': permitidos,
        'denegados': denegados,
        'promedio': round(promedio or 0,2),
        'eventos': eventos,
        'revision': revision,
        'detecciones_live': detecciones_live,

    })

def exportar_pdf(request):

    response = HttpResponse(
        content_type='application/pdf'
    )

    response[
        'Content-Disposition'
    ] = (
        'attachment; filename="reporte_biometrico.pdf"'
    )

    doc = SimpleDocTemplate(

        response,

        pagesize=letter

    )

    elementos = []

    estilos = getSampleStyleSheet()


    # =========================
    # TITULO
    # =========================

    titulo = Paragraph(

        'Reporte Biométrico Diario',

        estilos['Title']

    )

    elementos.append(titulo)

    elementos.append(
        Spacer(1, 20)
    )


    # =========================
    # KPIs
    # =========================

    hoy = now().date()

    permitidos = Acceso.objects.filter(
        resultado='PERMITIDO',
        fecha_hora__date=hoy
    ).count()

    denegados = Acceso.objects.filter(
        resultado='DENEGADO',
        fecha_hora__date=hoy
    ).count()

    revision = Acceso.objects.filter(
        resultado='REVISION',
        fecha_hora__date=hoy
    ).count()


    tabla_kpi = Table([

        ['Métrica', 'Valor'],

        ['Permitidos', permitidos],

        ['Denegados', denegados],

        ['Revisión', revision],

    ])


    tabla_kpi.setStyle(

        TableStyle([

            ('BACKGROUND', (0,0), (-1,0), colors.black),

            ('TEXTCOLOR', (0,0), (-1,0), colors.white),

            ('GRID', (0,0), (-1,-1), 1, colors.gray),

            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),

        ])

    )

    elementos.append(tabla_kpi)

    elementos.append(
        Spacer(1, 30)
    )


    # =========================
    # ACCESOS
    # =========================

    accesos = Acceso.objects.order_by(
        '-fecha_hora'
    )[:20]


    data = [[

        'Usuario',

        'Resultado',

        'Coincidencia',

        'Fecha y Hora'

    ]]


    for acceso in accesos:

        usuario = (

            acceso.persona.nombre

            if acceso.persona

            else 'Desconocido'

        )

        data.append([

            usuario,

            acceso.resultado,

            f'{acceso.coincidencia}%',

            acceso.fecha_hora.strftime(
                '%d/%m/%Y %H:%M'
            )

        ])

    tabla = Table(data)

    tabla.setStyle(

        TableStyle([

            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),

            ('TEXTCOLOR', (0,0), (-1,0), colors.white),

            ('GRID', (0,0), (-1,-1), 1, colors.gray),

            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),

        ])

    )



    elementos.append(tabla)

    elementos.append(
        Spacer(1, 40)
    )

    estilo_footer = ParagraphStyle(

        'Footer',

        parent=estilos['Normal'],

        alignment=TA_CENTER,

        textColor=colors.gray,

        fontSize=9,

    )

    fecha_reporte = Paragraph(

        f'Reporte generado: {now().strftime("%d/%m/%Y %H:%M")}',

        estilo_footer

    )

    elementos.append(fecha_reporte)

    elementos.append(
        Spacer(1, 20)
    )

    doc.build(elementos)

    

    return response