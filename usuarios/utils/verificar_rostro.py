import cv2
import os

from usuarios.models import Persona


modelo_path = 'modelo/modelo_lbph.yml'


recognizer = cv2.face.LBPHFaceRecognizer_create(
    radius=2,
    neighbors=16,
    grid_x=8,
    grid_y=8
)

if os.path.exists(modelo_path):

    try:

        print(
            "MODELO:",
            os.path.abspath(modelo_path)
        )

        recognizer.read(
            modelo_path
        )

        print(
            "MODELO CARGADO"
        )

    except Exception as e:

        print(
            "ERROR CARGANDO MODELO:",
            e
        )


face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    'haarcascade_frontalface_default.xml'
)


def reconocer_rostro(imagen_path):

    if not os.path.exists(modelo_path):

        print(
            "NO EXISTE MODELO"
        )

        return None

    try:

        recognizer.read(
            modelo_path
        )

    except Exception as e:

        print(
            "MODELO CORRUPTO:",
            e
        )

        return None
        
    imagen = cv2.imread(imagen_path)

    if imagen is None:
        return None

    gray = cv2.cvtColor(
        imagen,
        cv2.COLOR_BGR2GRAY
    )

    rostros = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(50, 50)
    )

    for (x, y, w, h) in rostros:

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

        label, confianza = recognizer.predict(
            rostro
        )

        print(
            'LABEL:',
            label,
            'CONF:',
            confianza
        )

        if confianza < 160:

            try:

                persona = Persona.objects.get(
                    id=label
                )

                porcentaje = max(

                    1,

                    int(

                        100 - (
                            confianza / 2
                        )

                    )

                )

                return {
                    'persona': persona,
                    'confianza': porcentaje
                }

            except Persona.DoesNotExist:
                pass

    return None