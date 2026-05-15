import cv2
import os
import numpy as np

from usuarios.models import RostroCapturado


def entrenar_modelo():

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=2,
        neighbors=16,
        grid_x=8,
        grid_y=8
    )

    rostros = []

    labels = []

    dataset = RostroCapturado.objects.all()

    for rostro_db in dataset:

        ruta_imagen = rostro_db.imagen.path

        imagen = cv2.imread(
            ruta_imagen,
            cv2.IMREAD_GRAYSCALE
        )

        if imagen is None:
            continue

        imagen = cv2.resize(
            imagen,
            (300, 300)
        )

        rostros.append(imagen)

        labels.append(
            rostro_db.persona.id
        )

    if len(rostros) == 0:
        return

    recognizer.train(
        rostros,
        np.array(labels)
    )

    os.makedirs('modelo', exist_ok=True)

    recognizer.save(
        'modelo/modelo_lbph.yml'
    )

    print("MODELO ENTRENADO")