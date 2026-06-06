import os
import django
import cv2
import numpy as np


os.environ.setdefault(

    'DJANGO_SETTINGS_MODULE',

    'facial_secure.settings'

)

django.setup()


from usuarios.models import RostroCapturado


print('\nINICIANDO ENTRENAMIENTO...\n')


recognizer = cv2.face.LBPHFaceRecognizer_create(

    radius=2,
    neighbors=16,
    grid_x=8,
    grid_y=8

)


rostros = []

labels = []


dataset = RostroCapturado.objects.all()


print(
    f'Capturas encontradas: {dataset.count()}\n'
)


for rostro_db in dataset:

    try:

        ruta_imagen = rostro_db.imagen.path

        if not os.path.exists(ruta_imagen):

            print(
                f'Imagen no existe: {ruta_imagen}'
            )

            continue

        imagen = cv2.imread(

            ruta_imagen,

            cv2.IMREAD_GRAYSCALE

        )

        if imagen is None:

            print(
                f'Error leyendo: {ruta_imagen}'
            )

            continue

        imagen = cv2.resize(

            imagen,

            (160,160)

        )

        persona_id = rostro_db.persona.id

        rostros.append(imagen)

        labels.append(persona_id)

        print(

            f'OK -> Persona ID: '

            f'{persona_id}'

        )

    except Exception as e:

        print(
            'ERROR:',
            e
        )  


print('\n====================')
print(f'Total rostros: {len(rostros)}')
print('====================\n')


if len(rostros) == 0:

    print(
        'NO HAY ROSTROS PARA ENTRENAR'
    )

    exit()


recognizer.train(

    rostros,

    np.array(labels)

)


os.makedirs(

    'modelo',

    exist_ok=True

)


recognizer.save(
    'modelo/modelo_lbph.yml'
)


print('\nMODELO ENTRENADO CORRECTAMENTE\n')