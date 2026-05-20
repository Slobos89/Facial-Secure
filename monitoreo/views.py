import cv2
import base64
import numpy as np
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from usuarios.models import Acceso


modelo = cv2.face.LBPHFaceRecognizer_create()

modelo.read(
    'modelo/modelo_lbph.yml'
)

def monitoreo(request):

    accesos = Acceso.objects.order_by(
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


        detector = cv2.CascadeClassifier(

            cv2.data.haarcascades +
            'haarcascade_frontalface_default.xml'

        )


        faces = detector.detectMultiScale(

            gray,

            scaleFactor=1.1,

            minNeighbors=5,

            minSize=(60,60)

        )


        resultados = []

        

        for(x,y,w,h) in faces:

            rostro = gray[
                y:y+h,
                x:x+w
            ]

            rostro = cv2.resize(
                rostro,
                (200,200)
            )


            usuario_id, confianza = modelo.predict(
                rostro
            )

            print(

                'ID:',
                usuario_id,

                'Confianza:',
                confianza

            )


            coincidencia = max(

                0,

                min(

                    100,

                    int(

                        100 * (
                            1 - (confianza / 120)
                        )

                    )

                )

            )


            nombre = 'Desconocido'

            estado = 'DENEGADO'


            try:

                acceso = Acceso.objects.get(
                    persona_id=usuario_id
                )

                nombre = acceso.persona.nombre


                if coincidencia >= 80:

                    estado = 'PERMITIDO'

                elif coincidencia >= 50:

                    estado = 'REVISION'

                else:

                    estado = 'DENEGADO'

            except:

                pass


            resultados.append({

                'id': f'{x}-{y}-{w}-{h}',

                'x': int(x),
                'y': int(y),
                'w': int(w),
                'h': int(h),

                'estado': estado,

                'coincidencia': coincidencia,

                'nombre': nombre

            })


        return JsonResponse({

            'rostros': resultados

        })


    return JsonResponse({

        'rostros': []

    })