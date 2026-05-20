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

    recognizer.read(modelo_path)


face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    'haarcascade_frontalface_default.xml'
)


def reconocer_rostro(imagen_path):

    if not os.path.exists(modelo_path):
        
        return None
    
    recognizer.read(modelo_path)
        
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

        rostro = gray[y:y+h, x:x+w]

        rostro = cv2.resize(
            rostro,
            (300, 300)
        )

        label, confianza = recognizer.predict(
            rostro
        )

        if confianza < 80:

            try:

                persona = Persona.objects.get(
                    id=label
                )

                porcentaje = max(
                    0,
                    min(
                        100,
                        round(

                            max(

                                0,

                                min(

                                    100,

                                    100 * (
                                        1 - (confianza / 120)
                                    )

                                )

                            ),

                            2

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