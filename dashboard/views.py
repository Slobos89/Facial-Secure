from django.shortcuts import render
from django.db.models import Avg, Count, Q
from django.utils.timezone import now
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.db.models.functions import ExtractHour
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
from django.contrib.auth.decorators import login_required


@login_required
def dashboard(request):
    hoy = now()
    ayer = (hoy - timedelta(days=1)).date()

    periodo = request.GET.get('periodo', 'todo')

    filtro_fecha = {}
    if periodo == 'hoy':
        filtro_fecha['fecha_hora__date'] = hoy.date()
    elif periodo == '7':
        filtro_fecha['fecha_hora__date__gte'] = (hoy - timedelta(days=7)).date()
    elif periodo == '30':
        filtro_fecha['fecha_hora__date__gte'] = (hoy - timedelta(days=30)).date()
    elif periodo == 'todo':
        filtro_fecha = {}

    # 1. Conteo de personas registradas
    persona_counts = Persona.objects.aggregate(
        total=Count('id'),
        internos=Count('id', filter=Q(tipo_persona='interno')),
        gendarmes=Count('id', filter=Q(tipo_persona='gendarme')),
        externos=Count('id', filter=Q(tipo_persona='externo')),
    )
    total_personas = persona_counts['total']
    internos = persona_counts['internos']
    gendarmes = persona_counts['gendarmes']
    externos = persona_counts['externos']

    # 2. Métricas consolidadas de accesos en el periodo
    acceso_stats = Acceso.objects.filter(**filtro_fecha).aggregate(
        total=Count('id'),
        permitidos=Count('id', filter=Q(resultado__in=['PERMITIDO', 'APROBADO_MANUAL'])),
        denegados=Count('id', filter=Q(resultado__in=['DENEGADO', 'RECHAZADO'])),
        revision=Count('id', filter=Q(resultado='REVISION')),
        promedio=Avg('coincidencia', filter=Q(coincidencia__gt=0)),
        gendarmes_acc=Count('id', filter=Q(persona__tipo_persona='gendarme')),
        internos_acc=Count('id', filter=Q(persona__tipo_persona='interno')),
        externos_acc=Count('id', filter=Q(persona__tipo_persona='externo')),
        no_id_acc=Count('id', filter=Q(persona__isnull=True)),
    )
    accesos_hoy = acceso_stats['total']
    permitidos = acceso_stats['permitidos']
    denegados = acceso_stats['denegados']
    revision = acceso_stats['revision']
    promedio = acceso_stats['promedio'] or 0

    tasa_exito = round((permitidos / (accesos_hoy if accesos_hoy > 0 else 1)) * 100, 1)

    # 3. Comparativa de ayer para porcentaje de cambio
    permitidos_ayer = Acceso.objects.filter(
        resultado__in=['PERMITIDO', 'APROBADO_MANUAL'],
        fecha_hora__date=ayer
    ).count()

    if permitidos_ayer > 0:
        porcentaje_cambio = round(
            ((permitidos - permitidos_ayer) / permitidos_ayer) * 100,
            1
        )
    else:
        porcentaje_cambio = 0

    # 4. Alertas dinámicas
    alerta_texto = None
    alerta_tipo = None
    if denegados >= 10:
        alerta_texto = 'Alta cantidad de accesos denegados'
        alerta_tipo = 'critica'
    elif denegados >= 5:
        alerta_texto = 'Incremento de intentos fallidos'
        alerta_tipo = 'advertencia'

    detecciones_live = Acceso.objects.filter(
        fecha_hora__gte=timezone.now() - timedelta(minutes=1)
    ).count()

    # 5. Accesos recientes con select_related y foto segura filtrados por periodo
    recientes = Acceso.objects.filter(**filtro_fecha).select_related('persona').order_by('-fecha_hora')[:20]
    eventos = []
    for acceso in recientes:
        foto_url = ('/media/secure/' + acceso.foto_validacion.name) if acceso.foto_validacion else (
            ('/media/secure/' + acceso.persona.foto.name) if (acceso.persona and acceso.persona.foto) else '/static/img/no-face.jpg'
        )
        eventos.append({
            'id': acceso.id,
            'nombre': f"{acceso.persona.nombre} {acceso.persona.apellido}" if acceso.persona else (acceso.nombre_detectado or 'Desconocido'),
            'rut': acceso.persona.rut if acceso.persona else '---',
            'tipo': acceso.persona.get_tipo_persona_display() if acceso.persona else 'Externo / Intruso',
            'resultado': acceso.resultado,
            'coincidencia': round(acceso.coincidencia, 1),
            'camara': acceso.camara or 'Principal',
            'hora': acceso.fecha_hora.strftime('%H:%M:%S'),
            'fecha': acceso.fecha_hora.strftime('%d/%m/%Y'),
            'foto': foto_url
        })

    # 6. Agrupación por horas completa (00:00 a 23:00)
    horas_labels = [f"{h:02d}:00" for h in range(24)]
    horas_permitidos = [0] * 24
    horas_denegados = [0] * 24

    qs_horas = (
        Acceso.objects.filter(**filtro_fecha)
        .annotate(hora=ExtractHour('fecha_hora'))
        .values('hora', 'resultado')
        .annotate(total=Count('id'))
    )

    for item in qs_horas:
        h = item['hora']
        if h is not None and 0 <= h < 24:
            if item['resultado'] in ['PERMITIDO', 'APROBADO_MANUAL']:
                horas_permitidos[h] += item['total']
            else:
                horas_denegados[h] += item['total']

    # Distribución por Rol
    roles_chart = [
        acceso_stats['gendarmes_acc'],
        acceso_stats['internos_acc'],
        acceso_stats['externos_acc'],
        acceso_stats['no_id_acc'],
    ]

    contexto = {
        'total_personas': total_personas,
        'internos': internos,
        'gendarmes': gendarmes,
        'externos': externos,
        'accesos_hoy': accesos_hoy,
        'permitidos': permitidos,
        'denegados': denegados,
        'revision': revision,
        'tasa_exito': tasa_exito,
        'detecciones_live': detecciones_live,
        'promedio': round(promedio, 1),
        'recientes': recientes,
        'porcentaje_cambio': porcentaje_cambio,
        'eventos': eventos,
        'horas_labels': json.dumps(horas_labels),
        'horas_permitidos': json.dumps(horas_permitidos),
        'horas_denegados': json.dumps(horas_denegados),
        'estados_chart': json.dumps([permitidos, denegados, revision]),
        'roles_chart': json.dumps(roles_chart),
        'periodo': periodo,
        'alerta_texto': alerta_texto,
        'alerta_tipo': alerta_tipo,
        'camaras_activas': 1,
        'total_camaras': 1,
    }

    return render(
        request,
        'dashboard/dashboard.html',
        contexto
    )


@login_required
def dashboard_data(request):
    hoy = now()
    periodo = request.GET.get('periodo', 'todo')

    filtro_fecha = {}
    if periodo == 'hoy':
        filtro_fecha['fecha_hora__date'] = hoy.date()
    elif periodo == '7':
        filtro_fecha['fecha_hora__date__gte'] = (hoy - timedelta(days=7)).date()
    elif periodo == '30':
        filtro_fecha['fecha_hora__date__gte'] = (hoy - timedelta(days=30)).date()
    elif periodo == 'todo':
        filtro_fecha = {}

    acceso_stats = Acceso.objects.filter(**filtro_fecha).aggregate(
        permitidos=Count('id', filter=Q(resultado__in=['PERMITIDO', 'APROBADO_MANUAL'])),
        denegados=Count('id', filter=Q(resultado__in=['DENEGADO', 'RECHAZADO'])),
        revision=Count('id', filter=Q(resultado='REVISION')),
        promedio=Avg('coincidencia', filter=Q(coincidencia__gt=0)),
    )
    permitidos = acceso_stats['permitidos']
    denegados = acceso_stats['denegados']
    revision = acceso_stats['revision']
    promedio = acceso_stats['promedio'] or 0

    detecciones_live = Acceso.objects.filter(
        fecha_hora__gte=timezone.now() - timedelta(minutes=1)
    ).count()

    recientes = Acceso.objects.filter(**filtro_fecha).select_related('persona').order_by('-fecha_hora')[:20]

    eventos = []
    for acceso in recientes:
        foto_url = ('/media/secure/' + acceso.foto_validacion.name) if acceso.foto_validacion else (
            ('/media/secure/' + acceso.persona.foto.name) if (acceso.persona and acceso.persona.foto) else '/static/img/no-face.jpg'
        )
        eventos.append({
            'id': acceso.id,
            'nombre': f"{acceso.persona.nombre} {acceso.persona.apellido}" if acceso.persona else (acceso.nombre_detectado or 'Desconocido'),
            'rut': acceso.persona.rut if acceso.persona else '---',
            'tipo': acceso.persona.get_tipo_persona_display() if acceso.persona else 'Externo / Intruso',
            'resultado': acceso.resultado,
            'coincidencia': round(acceso.coincidencia, 1),
            'camara': acceso.camara or 'Principal',
            'hora': acceso.fecha_hora.strftime('%H:%M:%S'),
            'fecha': acceso.fecha_hora.strftime('%d/%m/%Y'),
            'foto': foto_url
        })

    return JsonResponse({
        'permitidos': permitidos,
        'denegados': denegados,
        'promedio': round(promedio, 1),
        'eventos': eventos,
        'revision': revision,
        'detecciones_live': detecciones_live,
    })

@login_required
def exportar_pdf(request):
    response = HttpResponse(content_type='application/pdf')
    filename = f"reporte_biometrico_{now().strftime('%Y%m%d_%H%M')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    hoy = now()
    periodo = request.GET.get('periodo', 'todo')
    periodo_texto = "Historial Completo (Global)"

    filtro_fecha = {}
    if periodo == 'hoy':
        filtro_fecha['fecha_hora__date'] = hoy.date()
        periodo_texto = f"Turno Actual - {hoy.strftime('%d/%m/%Y')}"
    elif periodo == '7':
        fecha_inicio = (hoy - timedelta(days=7)).date()
        filtro_fecha['fecha_hora__date__gte'] = fecha_inicio
        periodo_texto = f"Últimos 7 días (desde {fecha_inicio.strftime('%d/%m/%Y')})"
    elif periodo == '30':
        fecha_inicio = (hoy - timedelta(days=30)).date()
        filtro_fecha['fecha_hora__date__gte'] = fecha_inicio
        periodo_texto = f"Últimos 30 días (desde {fecha_inicio.strftime('%d/%m/%Y')})"

    # Configuración de documento (Carta con márgenes compactos de 0.5 pulgadas)
    doc = SimpleDocTemplate(
        response,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    elementos = []
    estilos = getSampleStyleSheet()

    # Paleta Corporativa
    COLOR_PRIMARY = colors.HexColor('#0F172A')
    COLOR_ACCENT = colors.HexColor('#2563EB')
    COLOR_BG_LIGHT = colors.HexColor('#F8FAFC')
    COLOR_BORDER = colors.HexColor('#CBD5E1')
    COLOR_MUTED = colors.HexColor('#64748B')

    # Estilos de Texto
    style_title = ParagraphStyle(
        'HeaderTitle',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=19,
        textColor=COLOR_PRIMARY
    )
    style_subtitle = ParagraphStyle(
        'HeaderSubtitle',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=COLOR_MUTED
    )
    style_meta_val = ParagraphStyle(
        'MetaVal',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=COLOR_MUTED,
        alignment=TA_CENTER
    )
    style_section_title = ParagraphStyle(
        'SectionTitle',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=COLOR_PRIMARY,
        spaceAfter=6
    )
    style_th = ParagraphStyle(
        'TableHead',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=TA_CENTER
    )
    style_td = ParagraphStyle(
        'TableBody',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=COLOR_PRIMARY
    )
    style_td_center = ParagraphStyle(
        'TableBodyCenter',
        parent=style_td,
        alignment=TA_CENTER
    )
    style_footer = ParagraphStyle(
        'FooterStyle',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=COLOR_MUTED,
        alignment=TA_CENTER
    )

    # ========================================================
    # 1. ENCABEZADO INSTITUCIONAL
    # ========================================================
    usuario_operador = request.user.get_full_name() or request.user.username
    rol_operador = getattr(getattr(request.user, 'perfilusuario', None), 'rol', 'OPERADOR')

    header_data = [
        [
            Paragraph("<b>FacIAL Secure</b> | Control Penitenciario", style_title),
            Paragraph(f"<b>Emisión:</b> {now().strftime('%d/%m/%Y %H:%M')}<br/><b>Operador:</b> {usuario_operador} ({rol_operador})", style_meta_val)
        ],
        [
            Paragraph(f"Informe de Auditoría Biometría • <b>Período:</b> {periodo_texto}", style_subtitle),
            Paragraph("<b>Entorno:</b> Edge Local • Zero-Knowledge<br/><b>Estado:</b> Operativo / En Línea", style_meta_val)
        ]
    ]

    header_table = Table(header_data, colWidths=[360, 180])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('LINEBELOW', (0,1), (-1,1), 1.5, COLOR_ACCENT),
    ]))
    elementos.append(header_table)
    elementos.append(Spacer(1, 10))

    # ========================================================
    # 2. MÉTRICAS CONSOLIDADAS Y KPIs DEL PERÍODO
    # ========================================================
    stats = Acceso.objects.filter(**filtro_fecha).aggregate(
        total=Count('id'),
        permitidos=Count('id', filter=Q(resultado__in=['PERMITIDO', 'APROBADO_MANUAL'])),
        denegados=Count('id', filter=Q(resultado__in=['DENEGADO', 'RECHAZADO'])),
        revision=Count('id', filter=Q(resultado='REVISION')),
        promedio_ia=Avg('coincidencia', filter=Q(coincidencia__gt=0)),
    )

    total_acc = stats['total'] or 0
    perm = stats['permitidos'] or 0
    den = stats['denegados'] or 0
    rev = stats['revision'] or 0
    prom_ia = round(stats['promedio_ia'] or 0, 1)
    tasa_exito = round((perm / total_acc * 100), 1) if total_acc > 0 else 100.0

    kpi_card_data = [
        [
            Paragraph(f"<font size=12><b>{total_acc}</b></font><br/><font color='#64748B' size=6.5>TOTAL ACCESOS</font>", style_td_center),
            Paragraph(f"<font size=12 color='#16A34A'><b>{perm}</b></font><br/><font color='#64748B' size=6.5>PERMITIDOS</font>", style_td_center),
            Paragraph(f"<font size=12 color='#DC2626'><b>{den}</b></font><br/><font color='#64748B' size=6.5>DENEGADOS</font>", style_td_center),
            Paragraph(f"<font size=12 color='#D97706'><b>{rev}</b></font><br/><font color='#64748B' size=6.5>EN REVISIÓN</font>", style_td_center),
            Paragraph(f"<font size=12 color='#2563EB'><b>{prom_ia}%</b></font><br/><font color='#64748B' size=6.5>PRECISIÓN IA</font>", style_td_center),
            Paragraph(f"<font size=12><b>{tasa_exito}%</b></font><br/><font color='#64748B' size=6.5>TASA ÉXITO</font>", style_td_center),
        ]
    ]

    kpi_table = Table(kpi_card_data, colWidths=[90, 90, 90, 90, 90, 90])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_BG_LIGHT),
        ('BOX', (0,0), (-1,-1), 1, COLOR_BORDER),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    elementos.append(kpi_table)
    elementos.append(Spacer(1, 12))

    # ========================================================
    # 3. TABLA DE REGISTROS DE ACCESO DEL PERÍODO
    # ========================================================
    elementos.append(Paragraph(f"Registro Cronológico de Accesos Biométricos ({periodo_texto})", style_section_title))

    accesos = Acceso.objects.filter(**filtro_fecha).select_related('persona').order_by('-fecha_hora')[:30]

    tabla_data = [[
        Paragraph("<b>USUARIO</b>", style_th),
        Paragraph("<b>RUT / ID</b>", style_th),
        Paragraph("<b>TIPO / ROL</b>", style_th),
        Paragraph("<b>CÁMARA</b>", style_th),
        Paragraph("<b>ESTADO</b>", style_th),
        Paragraph("<b>PRECISIÓN</b>", style_th),
        Paragraph("<b>FECHA Y HORA</b>", style_th),
    ]]

    for acc in accesos:
        if acc.persona:
            nombre = f"{acc.persona.nombre} {acc.persona.apellido}"
            rut = acc.persona.rut
            tipo = acc.persona.get_tipo_persona_display()
        else:
            nombre = acc.nombre_detectado or "Sujeto No Identificado"
            rut = "---"
            tipo = "Externo / No registrado"

        res = acc.resultado
        if res in ['PERMITIDO', 'APROBADO_MANUAL']:
            res_html = f"<font color='#16A34A'><b>{res}</b></font>"
        elif res in ['DENEGADO', 'RECHAZADO']:
            res_html = f"<font color='#DC2626'><b>{res}</b></font>"
        else:
            res_html = f"<font color='#D97706'><b>{res}</b></font>"

        tabla_data.append([
            Paragraph(nombre, style_td),
            Paragraph(rut, style_td_center),
            Paragraph(tipo, style_td),
            Paragraph(acc.camara or 'Principal', style_td_center),
            Paragraph(res_html, style_td_center),
            Paragraph(f"{acc.coincidencia:.1f}%", style_td_center),
            Paragraph(acc.fecha_hora.strftime('%d/%m/%Y %H:%M:%S'), style_td_center),
        ])

    if len(tabla_data) == 1:
        tabla_data.append([
            Paragraph("<font color='#64748B'><i>No se registraron accesos en este período</i></font>", style_td_center),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("", style_td),
            Paragraph("", style_td),
        ])

    col_widths = [110, 75, 75, 70, 75, 55, 80]
    tabla_accesos = Table(tabla_data, colWidths=col_widths, repeatRows=1)

    t_style = [
        ('BACKGROUND', (0,0), (-1,0), COLOR_PRIMARY),
        ('BOX', (0,0), (-1,-1), 1, COLOR_BORDER),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]

    for row_idx in range(1, len(tabla_data)):
        if row_idx % 2 == 0:
            t_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), COLOR_BG_LIGHT))

    tabla_accesos.setStyle(TableStyle(t_style))
    elementos.append(tabla_accesos)
    elementos.append(Spacer(1, 14))

    # ========================================================
    # 4. PIE DE PÁGINA Y SELLO DE INTEGRIDAD
    # ========================================================
    elementos.append(Paragraph(
        "<b>Documento de Carácter Oficial y Confidencial</b> • Generado por la plataforma FacIAL Secure bajo estándares de Protección de Datos (Ley N° 19.628).",
        style_footer
    ))

    doc.build(elementos)
    return response
