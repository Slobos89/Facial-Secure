import os
import cv2
import base64
import numpy as np
import uuid
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from usuarios.models import Acceso, Persona
from django.contrib.auth.decorators import login_required

# ==========================================
# OPTIMIZACIÓN: Cargar detector y modelo 1 sola vez en memoria
# ==========================================
detector_rostros = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

modelo_path = 'modelo/modelo_lbph.yml'
modelo = cv2.face.LBPHFaceRecognizer_create(
    radius=2,
    neighbors=16,
    grid_x=8,
    grid_y=8
)
ultimo_modelo_mtime = 0

def get_modelo():
    """Recarga el modelo en caliente si fue actualizado tras un nuevo enrolamiento."""
    global modelo, ultimo_modelo_mtime
    if os.path.exists(modelo_path):
        try:
            mtime = os.path.getmtime(modelo_path)
            if mtime != ultimo_modelo_mtime:
                modelo.read(modelo_path)
                ultimo_modelo_mtime = mtime
                print('MODELO MONITOREO ACTUALIZADO EN MEMORIA')
        except Exception as e:
            print('ERROR MODELO MONITOREO:', e)
    return modelo

# Carga inicial
get_modelo()


@login_required
def monitoreo(request):

    accesos = Acceso.objects.select_related('persona').order_by(
        '-fecha_hora'
    )[:20]

    return render(

        request,

        'monitoreo/monitoreo.html',

        {

            'accesos': accesos

        }

    )

@csrf_exempt
@login_required
def detectar_rostros(request):



    if request.method == 'POST':

        foto_base64 = request.POST.get(
            'foto_base64'
        )

        if not foto_base64:

            return JsonResponse({

                'rostros': []

            })


        formato, imgstr = foto_base64.split(';base64,')

        img_bytes = base64.b64decode(
            imgstr
        )


        npimg = np.frombuffer(
            img_bytes,
            np.uint8
        )

        frame = cv2.imdecode(
            npimg,
            cv2.IMREAD_COLOR
        )


        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY
        )


        # Detección ultra rápida con clasificador precargado
        faces = detector_rostros.detectMultiScale(

            gray,

            scaleFactor=1.1,

            minNeighbors=5,

            minSize=(60,60)

        )


        resultados = []

        modelo_actual = get_modelo()

        for(x,y,w,h) in faces:

            padding_x = int(w * 0.25)

            padding_y = int(h * 0.35)


            x1 = max(0, x - padding_x)

            y1 = max(0, y - padding_y)

            x2 = min(
                gray.shape[1],
                x + w + padding_x
            )

            y2 = min(
                gray.shape[0],
                y + h + padding_y
            )


            rostro = gray[
                y1:y2,
                x1:x2
            ]

            rostro = cv2.resize(
                rostro,
                (160,160)
            )


            usuario_id, confianza = modelo_actual.predict(
                rostro
            )

            try:

                persona = Persona.objects.get(
                    id=usuario_id
                )

                print(
                    f'RECONOCIDO -> '
                    f'{persona.nombre} '
                    f'{persona.apellido} '
                    f'Confianza={confianza}'
                )

            except:
                pass

            print(

                'ID:',
                usuario_id,

                'Confianza:',
                confianza

            )


            coincidencia = max(

                1,

                int(

                    100 - (
                        confianza / 2
                    )

                )

            )


            nombre = 'Desconocido'

            estado = 'DENEGADO'

            persona = None


            try:

                persona = Persona.objects.get(
                    id=usuario_id
                )

                nombre = (
                    f'{persona.nombre} '
                    f'{persona.apellido}'
                )


                if coincidencia >= 55:

                    estado = 'PERMITIDO'

                elif coincidencia >= 40:

                    estado = 'REVISION'

                else:

                    estado = 'DENEGADO'


            except Persona.DoesNotExist:

                nombre = 'Desconocido'

                estado = 'DENEGADO'


            # =========================
            # GUARDAR FOTO ROSTRO
            # =========================

            rostro_color = frame[
                y1:y2,
                x1:x2
            ]


            _, buffer = cv2.imencode(
                '.jpg',
                rostro_color
            )


            nombre_archivo = (
                f'{uuid.uuid4()}.jpg'
            )


            # =========================
            # CREAR ACCESO
            # =========================

            acceso = Acceso.objects.create(

                persona=persona,

                nombre_detectado=nombre,

                coincidencia=coincidencia,

                resultado=estado,

                camara='Camara Principal'

            )


            # =========================
            # FOTO VALIDACION
            # =========================

            from usuarios.utils.security import encrypt_bytes
            
            encrypted_bytes = encrypt_bytes(buffer.tobytes())

            acceso.foto_validacion.save(

                nombre_archivo,

                ContentFile(
                    encrypted_bytes
                ),

                save=True

            )

            resultados.append({
                'id': f'{x}-{y}-{w}-{h}',
                'x': int(x),
                'y': int(y),
                'w': int(w),
                'h': int(h),
                'estado': estado,
                'coincidencia': coincidencia,
                'nombre': nombre,
                'tipo': persona.get_tipo_persona_display() if persona else 'Desconocido',
                'rut': persona.rut if persona else '---',
                'hora': acceso.fecha_hora.strftime('%H:%M:%S')
            })


        return JsonResponse({

            'rostros': resultados

        })


    return JsonResponse({

        'rostros': []

    })