import tempfile
import os
import base64
import json
import uuid
import subprocess
import sys
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.db.models import OuterRef, Subquery, Q
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
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from .models import PerfilUsuario



@login_required
def usuarios(request):

    ultimo_acceso = Acceso.objects.filter(
        persona=OuterRef('pk')
    ).order_by('-fecha_hora')


    internos = Persona.objects.filter(
        tipo_persona='interno'
    ).annotate(
        ultimo_acceso=Subquery(
            ultimo_acceso.values('fecha_hora')[:1]
        )
    )

    gendarmes_lista = Persona.objects.filter(
        tipo_persona='gendarme'
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

    for persona in internos:
        if persona.foto:
            persona.preview_facial = "/media/secure/" + persona.foto.name
        else:
            persona.preview_facial = ""

    for persona in gendarmes_lista:
        if persona.foto:
            persona.preview_facial = "/media/secure/" + persona.foto.name
        else:
            persona.preview_facial = ""

    for persona in externos:
        if persona.foto:
            persona.preview_facial = "/media/secure/" + persona.foto.name
        else:
            persona.preview_facial = ""

    total_usuarios = Persona.objects.count()

    usuarios_activos = Persona.objects.filter(
        estado='activo'
    ).count()

    usuarios_bloqueados = Persona.objects.filter(
        estado='bloqueado'
    ).count()

    biometrias = Persona.objects.filter(
        Q(biometria_facial=True) | (Q(foto__isnull=False) & ~Q(foto='')) | Q(rostros__isnull=False)
    ).distinct().count()

    

    return render(
        request,
        'usuarios/usuarios.html',
        {
            'internos': internos,
            'gendarmes_lista': gendarmes_lista,
            'externos': externos,
            'total_usuarios': total_usuarios,
            'usuarios_activos': usuarios_activos,
            'usuarios_bloqueados': usuarios_bloqueados,
            'biometrias': biometrias,
        }
    )


@login_required
def crear_persona(request):

    if request.method == 'POST':

        form = PersonaForm(request.POST)

        if form.is_valid():

            persona = form.save()

            huella_tpl = request.POST.get('huella_template')
            huella_cal = int(request.POST.get('huella_calidad') or 0)
            huella_fmt = request.POST.get('huella_formato') or 'ANSI378'

            if huella_tpl and len(huella_tpl.strip()) > 10:
                HuellaDactilar.objects.create(
                    persona=persona,
                    template=huella_tpl.strip(),
                    calidad=huella_cal,
                    formato=huella_fmt
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
            # Entrenamiento Incremental Zero-Knowledge automático
            entrenar_modelo()

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

@login_required
def registrar_gendarme(request):

    if request.method == 'POST':

        username = request.POST.get('username')
        password = request.POST.get('password')
        nombre = request.POST.get('nombre')
        apellido = request.POST.get('apellido')
        rut = request.POST.get('rut')

        # =====================
        # VALIDACIONES
        # =====================

        # 1. Campos vacíos
        if not username or not password or not nombre or not apellido or not rut:
            messages.error(request, 'Todos los campos son obligatorios.')
            return redirect('registrar_gendarme')

        # 2. Fuerza de la contraseña
        if len(password) < 8:
            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
            return redirect('registrar_gendarme')

        # 3. Validación Algorítmica de RUT Chileno
        rut_clean = rut.replace('.', '').replace('-', '').upper()
        if len(rut_clean) < 2:
            messages.error(request, 'El RUT ingresado no tiene un formato válido.')
            return redirect('registrar_gendarme')
            
        cuerpo = rut_clean[:-1]
        dv = rut_clean[-1]
        
        if not cuerpo.isdigit():
            messages.error(request, 'El cuerpo del RUT solo debe contener números.')
            return redirect('registrar_gendarme')

        suma = 0
        multiplo = 2
        for c in reversed(cuerpo):
            suma += int(c) * multiplo
            multiplo = multiplo + 1 if multiplo < 7 else 2

        dv_esperado = 11 - (suma % 11)
        dv_calculado = '0' if dv_esperado == 11 else ('K' if dv_esperado == 10 else str(dv_esperado))

        if dv != dv_calculado:
            messages.error(request, 'El RUT ingresado no es válido (Dígito Verificador incorrecto).')
            return redirect('registrar_gendarme')

        # 4. Duplicados en BD
        if User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya está en uso.')
            return redirect('registrar_gendarme')

        if Persona.objects.filter(rut=rut).exists():
            messages.error(request, 'El RUT ya está registrado en el sistema.')
            return redirect('registrar_gendarme')

        # =====================
        # CREAR PERSONA
        # =====================

        persona = Persona.objects.create(

            nombre=nombre,
            apellido=apellido,
            rut=rut,
            tipo_persona='gendarme',
            estado='activo'
        )

        # =====================
        # CREAR USER DJANGO
        # =====================

        user = User.objects.create_user(

            username=username,
            password=password,
            first_name=nombre,
            last_name=apellido
        )

        # =====================
        # PERFIL
        # =====================

        perfil = user.perfilusuario

        perfil.persona = persona
        perfil.rol = 'GENDARME'

        perfil.save()

        messages.success(
            request,
            'Gendarme registrado correctamente'
        )

        return redirect('usuarios')

    return render(
        request,
        'usuarios/registrar_gendarme.html'
    )

    

@login_required
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

@login_required
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

@login_required
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

@login_required
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

@login_required
def editar_usuario(request, persona_id):

    persona = Persona.objects.get(
        id=persona_id
    )

    if request.method == 'POST':

        persona.nombre = request.POST.get(
            'nombre'
        )

        persona.apellido = request.POST.get(
            'apellido'
        )

        persona.rut = request.POST.get(
            'rut'
        )

        persona.estado = request.POST.get(
            'estado'
        )

        persona.save()

        messages.success(

            request,

            'Usuario actualizado correctamente'
        )

        return redirect(
            'usuarios'
        )

    primer_rostro = (
        persona.rostros.first()
    )

    huella = HuellaDactilar.objects.filter(
        persona=persona
    ).first()

    return render(

        request,

        'usuarios/editar_usuario.html',

        {

            'persona': persona,
            'primer_rostro': primer_rostro,
            'huella': huella,

        }
    )

@login_required
def reenrolar_rostro(request, persona_id):

    if request.method != 'POST':

        return JsonResponse({
            'success': False,
            'error': 'Método no permitido'
        })

    persona = get_object_or_404(
        Persona,
        id=persona_id
    )

    capturas_json = request.POST.get(
        'capturas'
    )

    if not capturas_json:

        return JsonResponse({
            'success': False,
            'error': 'No se recibieron capturas'
        })

    # Eliminar dataset anterior

    persona.rostros.all().delete()

    capturas = json.loads(
        capturas_json
    )

    contador = 0

    for foto_data in capturas:

        try:

            format, imgstr = foto_data.split(
                ';base64,'
            )

            image_data = base64.b64decode(
                imgstr
            )

            image_pil = Image.open(
                BytesIO(image_data)
            )

            rostro = detectar_y_recortar_rostro(
                image_pil
            )

            if rostro is None:
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

                f'{persona.rut}_reenrolado_{contador}.jpg',

                ContentFile(
                    rostro_io.getvalue()
                ),

                save=True

            )

            contador += 1

        except Exception as e:

            print(
                'ERROR REENROLAMIENTO:',
                e
            )

    # Opcional

    try:

        entrenar_modelo()

    except Exception as e:

        print(
            'ERROR ENTRENANDO:',
            e
        )

    return JsonResponse({

        'success': True,

        'capturas': contador

    })

@csrf_exempt
@login_required
def registrar_huella(request, persona_id):
    persona = get_object_or_404(Persona, id=persona_id)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            data = request.POST

        template = data.get('template') or data.get('huella_template') or data.get('template_base64')
        calidad = int(data.get('calidad') or data.get('huella_calidad') or 0)
        formato = data.get('formato') or data.get('huella_formato') or 'ANSI378'

        # Si no vino template en el POST, intentar capturarlo directamente del sensor SecuGen
        if not template:
            from .utils.secugen_driver import capturar_huella_nativo
            resultado = capturar_huella_nativo(timeout_ms=10000, quality_min=40)
            if not resultado.get('success'):
                return JsonResponse({
                    'success': False,
                    'error': resultado.get('error', 'No se pudo capturar la huella del sensor.')
                })
            template = resultado.get('template')
            calidad = resultado.get('calidad', calidad)
            formato = resultado.get('formato', formato)

        if not template or len(template.strip()) < 10:
            return JsonResponse({
                'success': False,
                'error': 'El template dactilar recibido no es válido.'
            })

        huella, _ = HuellaDactilar.objects.update_or_create(
            persona=persona,
            defaults={
                'template': template.strip(),
                'calidad': calidad,
                'formato': formato
            }
        )

        return JsonResponse({
            'success': True,
            'mensaje': f'Huella dactilar de {persona.nombre} {persona.apellido} registrada exitosamente.',
            'calidad': calidad,
            'persona_id': persona.id
        })

    return render(request, 'usuarios/registrar_huella.html', {
        'persona': persona
    })
from django.http import HttpResponse, Http404
import os
from django.conf import settings
from .utils.security import decrypt_bytes

@login_required
def ver_foto_segura(request, ruta):
    ruta_completa = os.path.join(settings.MEDIA_ROOT, ruta)
    
    if not os.path.exists(ruta_completa):
        raise Http404('Imagen no encontrada')
        
    try:
        with open(ruta_completa, 'rb') as f:
            datos = f.read()
            
        try:
            datos_descifrados = decrypt_bytes(datos)
        except Exception:
            datos_descifrados = datos
            
        return HttpResponse(datos_descifrados, content_type='image/jpeg')
    except Exception as e:
        raise Http404('Error leyendo archivo')


from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required
def api_capturar_huella_sensor(request):
    from .utils.secugen_driver import capturar_huella_nativo
    try:
        timeout_ms = int(request.GET.get("timeout", 10000))
    except (ValueError, TypeError):
        timeout_ms = 10000

    resultado = capturar_huella_nativo(timeout_ms=timeout_ms, quality_min=40)
    return JsonResponse(resultado)

def api_estado_sensor(request):
    from .utils.secugen_driver import verificar_sensor_conectado
    conectado, mensaje = verificar_sensor_conectado()
    return JsonResponse({"conectado": conectado, "mensaje": mensaje})


@login_required
def perfil_persona_ajax(request, persona_id):
    persona = get_object_or_404(Persona, id=persona_id)
    foto_url = ('/media/secure/' + persona.foto.name) if persona.foto else '/static/img/no-face.jpg'

    ultimos_accesos = Acceso.objects.filter(persona=persona).order_by('-fecha_hora')[:5]
    accesos_list = []
    for acc in ultimos_accesos:
        accesos_list.append({
            'fecha': acc.fecha_hora.strftime('%d/%m/%Y %H:%M'),
            'camara': acc.camara or 'Principal',
            'resultado': acc.resultado,
            'coincidencia': round(acc.coincidencia, 1)
        })

    return JsonResponse({
        'id': persona.id,
        'nombre': persona.nombre,
        'apellido': persona.apellido,
        'nombre_completo': f"{persona.nombre} {persona.apellido}",
        'rut': persona.rut,
        'tipo': persona.get_tipo_persona_display(),
        'tipo_raw': persona.tipo_persona,
        'estado': persona.estado,
        'foto': foto_url,
        'rostros_count': persona.rostros.count(),
        'tiene_huella': hasattr(persona, 'huella') and persona.huella is not None,
        'fecha_registro': persona.fecha_registro.strftime('%d/%m/%Y') if persona.fecha_registro else '---',
        'accesos': accesos_list
    })


@csrf_exempt
@login_required
def toggle_estado_persona(request, persona_id):
    if request.user.perfilusuario.rol != 'ADMIN':
        return JsonResponse({'success': False, 'error': 'Solo administradores pueden modificar el estado del usuario.'}, status=403)

    persona = get_object_or_404(Persona, id=persona_id)
    persona.estado = 'bloqueado' if persona.estado == 'activo' else 'activo'
    persona.save()

    return JsonResponse({
        'success': True,
        'nuevo_estado': persona.estado,
        'nuevo_estado_display': persona.get_estado_display()
    })
