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


modelo_path = 'modelo/modelo_lbph.yml'

if os.path.exists(modelo_path):
    print("Modelo existente encontrado, usando UPDATE para preservar el conocimiento previo...")
    recognizer.read(modelo_path)
    recognizer.update(rostros, np.array(labels))
else:
    print("No hay modelo existente, usando TRAIN...")
    recognizer.train(rostros, np.array(labels))

os.makedirs('modelo', exist_ok=True)
recognizer.save(modelo_path)

print('\nBorrando evidencia cruda (Zero-Knowledge)...')
personas_procesadas = set()

for rostro_db in dataset:
    persona = rostro_db.persona
    
    # Conservar la primera captura como foto de perfil cifrada si no tiene
    if persona.id not in personas_procesadas and not persona.foto:
        if os.path.exists(rostro_db.imagen.path):
            from usuarios.utils.security import encrypt_bytes
            from django.core.files.base import ContentFile
            import uuid
            
            with open(rostro_db.imagen.path, 'rb') as f:
                encrypted_bytes = encrypt_bytes(f.read())
            
            filename = f"perfil_auto_{persona.id}_{uuid.uuid4().hex[:6]}.jpg"
            persona.foto.save(filename, ContentFile(encrypted_bytes), save=False)
            personas_procesadas.add(persona.id)

    if not persona.biometria_facial:
        persona.biometria_facial = True
        
    persona.save()
        
    ruta = rostro_db.imagen.path
    if os.path.exists(ruta):
        os.remove(ruta)
dataset.delete()

print('\nMODELO ENTRENADO Y DATASET DESTRUIDO CORRECTAMENTE\n')