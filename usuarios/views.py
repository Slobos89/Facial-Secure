import tempfile
import os
import base64
import json
import uuid
import subprocess
import sys
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.core.files.base import ContentFile
from django.db.models import OuterRef, Subquery
from django.contrib import messages
from .models import Persona, RostroCapturado, HuellaDactilar, Acceso
from .forms import PersonaForm
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
from .utils.reconocimiento import entrenar_modelo
from django.template.loader import render_to_string

from django.http import JsonResponse

from .utils.face_detection import detectar_y_recortar_rostro
from .utils.verificar_rostro import reconocer_rostro
from django.contrib.auth.decorators import login_required



@login_required
def usuarios(request):

    ultimo_acceso = Acceso.objects.filter(
        persona=OuterRef('pk')
    ).order_by('-fecha_hora')


    internos_gendarmes = Persona.objects.filter(
        tipo_persona__in=[
            'interno',
            'gendarme'
        ]
    ).annotate(
        ultimo_acceso=Subquery(
            ultimo_acceso.values('fecha_hora')[:1]
        )
    )

    externos = Persona.objects.filter(
        tipo_persona='externo'
    ).annotate(
        ultimo_acceso=Subquery(
            ultimo_acceso.values('fecha_hora')[:1]
        )
    )

    for persona in internos_gendarmes:

        primer_rostro = persona.rostros.first()

        if primer_rostro:

            persona.preview_facial = (
                primer_rostro.imagen.url
            )

        else:

            persona.preview_facial = ''


    for persona in externos:

        primer_rostro = persona.rostros.first()

        if primer_rostro:

            persona.preview_facial = (
                primer_rostro.imagen.url
            )

        else:

            persona.preview_facial = ''

    total_usuarios = Persona.objects.count()

    usuarios_activos = Persona.objects.filter(
        estado='activo'
    ).count()

    usuarios_bloqueados = Persona.objects.filter(
        estado='bloqueado'
    ).count()

    biometrias = Persona.objects.filter(
        rostros__isnull=False
    ).distinct().count()

    

    return render(
        request,
        'usuarios/usuarios.html',
        {
            'internos_gendarmes': internos_gendarmes,
            'externos': externos,
            'total_usuarios': total_usuarios,
            'usuarios_activos': usuarios_activos,
            'usuarios_bloqueados': usuarios_bloqueados,
            'biometrias': biometrias,
        }
    )


def crear_persona(request):

    if request.method == 'POST':

        form = PersonaForm(request.POST)

        if form.is_valid():

            persona = form.save()

            HuellaDactilar.objects.create(

                persona=persona,

                template=str(uuid.uuid4())
                #template=sensor.capture_template() cambiar a futuro con dispositivo fisico

            )

            capturas_json = request.POST.get(
                'capturas'
            )

            if capturas_json:

                capturas = json.loads(
                    capturas_json
                )

                contador = 0

                for foto_data in capturas:

                    try:

                        format, imgstr = foto_data.split(
                            ';base64,'
                        )

                        ext = format.split('/')[-1]

                        image_data = base64.b64decode(
                            imgstr
                        )

                        image_pil = Image.open(
                            BytesIO(image_data)
                        )

                        rostro = detectar_y_recortar_rostro(
                            image_pil
                        )

                        print('PROCESANDO CAPTURA')

                        if rostro is None:

                            print('NO DETECTADO')

                            continue

                        if rostro.mode == 'RGBA':

                            rostro = rostro.convert(
                                'RGB'
                            )

                        rostro_io = BytesIO()

                        rostro.save(
                            rostro_io,
                            format='JPEG'
                        )

                        rostro_db = RostroCapturado(
                            persona=persona
                        )

                        rostro_db.imagen.save(
                            f'{persona.rut}_{contador}.jpg',
                            ContentFile(
                                rostro_io.getvalue()
                            ),
                            save=True
                        )

                        print('ROSTRO GUARDADO')

                        contador += 1

                    except Exception as e:

                        print(
                            'ERROR CAPTURA:',
                            e
                        )

            #entrenar_modelo()

            return JsonResponse({

                'success': True

            })

    else:

        form = PersonaForm()

    return render(
        request,
        'usuarios/crear_persona.html',
        {
            'form': form
        }
    )

def validar_rostro(request):

    if request.method == 'POST':

        foto_data = request.POST.get(
            'foto_base64'
        )

        if not foto_data:

            return JsonResponse({
                'success': False
            })

        format, imgstr = foto_data.split(';base64,')

        image_data = base64.b64decode(imgstr)

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix='.jpg'
        )

        temp_file.write(image_data)

        temp_file.close()

        resultado = reconocer_rostro(
            temp_file.name
        )

        os.unlink(temp_file.name)

        if resultado:

            persona = resultado['persona']

            confianza = resultado['confianza']

            estado = (
                'PERMITIDO'
                if confianza >= 70
                else 'REVISION'
            )

            Acceso.objects.create(
                persona=persona,
                camara='Camara Principal',
                coincidencia=confianza,
                resultado=estado
            )

            return JsonResponse({

                'success': True,

                'persona': {
                    'nombre':
                        f'{persona.nombre} {persona.apellido}',
                    'rut':
                        persona.rut,
                    'tipo':
                        persona.tipo_persona
                },

                'confianza': confianza,

                'estado': estado,

                'huella': True
            })

        Acceso.objects.create(
            persona=None,
            camara='Camara Principal',
            coincidencia=0,
            resultado='DENEGADO'
        )

        return JsonResponse({

            'success': False,

            'estado': 'DENEGADO'
        })

    return JsonResponse({
        'success': False
    })

def historial_ajax(request):

    accesos = Acceso.objects.order_by(
        '-fecha_hora'
    )

    paginator = Paginator(
        accesos,
        10
    )

    page = request.GET.get('page')

    accesos = paginator.get_page(page)


    tabla_html = render_to_string(

        'validacion/partials/historial_tabla.html',

        {
            'accesos': accesos
        }

    )

    paginacion_html = render_to_string(

        'validacion/partials/paginacion.html',

        {
            'accesos': accesos
        }

    )

    return JsonResponse({

        'tabla': tabla_html,

        'paginacion': paginacion_html

    })

def live_feed(request):

    accesos = Acceso.objects.order_by(
        '-fecha_hora'
    )[:10]

    data = []

    for acceso in accesos:

        data.append({

            'persona':

                f'{acceso.persona.nombre} {acceso.persona.apellido}'

                if acceso.persona

                else 'Desconocido',

            'hora':

                acceso.fecha_hora.strftime(
                    '%H:%M:%S'
                ),

            'camara':

                acceso.camara,

            'resultado':

                acceso.resultado,

            'coincidencia':

                round(
                    acceso.coincidencia,
                    2
                )

        })

    return JsonResponse({

        'accesos': data

    })

def entrenar_ia(request):

    try:

        subprocess.run(

            [sys.executable, 'train_model.py'],

            check=True

        )

        messages.success(

            request,

            'Modelo entrenado correctamente'

        )

    except Exception as e:

        messages.error(

            request,

            f'Error entrenando modelo: {e}'

        )

    return redirect('usuarios')