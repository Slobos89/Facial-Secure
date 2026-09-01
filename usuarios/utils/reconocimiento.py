import cv2
import os
import uuid
import numpy as np
from django.core.files.base import ContentFile
from usuarios.models import RostroCapturado, Persona
from usuarios.utils.security import encrypt_bytes


def entrenar_modelo():
    """
    Entrenamiento Incremental Zero-Knowledge:
    1. Lee las capturas temporales recién registradas.
    2. Actualiza el modelo LBPH existente con recognizer.update() (o train si es nuevo).
    3. Guarda el modelo en 'modelo/modelo_lbph.yml'.
    4. Cifra la primera foto con AES-256 para asignarla como foto de perfil oficial.
    5. Destruye y borra todas las capturas crudas del disco y de la base de datos.
    """
    dataset = RostroCapturado.objects.all()
    if not dataset.exists():
        return

    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=2,
        neighbors=16,
        grid_x=8,
        grid_y=8
    )

    rostros = []
    labels = []

    for rostro_db in dataset:
        try:
            ruta_imagen = rostro_db.imagen.path
            if not os.path.exists(ruta_imagen):
                continue

            imagen = cv2.imread(ruta_imagen, cv2.IMREAD_GRAYSCALE)
            if imagen is None:
                continue

            imagen = cv2.resize(imagen, (160, 160))
            persona_id = rostro_db.persona.id

            rostros.append(imagen)
            labels.append(persona_id)
        except Exception as e:
            print(f"Error procesando captura {rostro_db.id}: {e}")

    if len(rostros) > 0:
        modelo_path = 'modelo/modelo_lbph.yml'
        os.makedirs('modelo', exist_ok=True)

        if os.path.exists(modelo_path):
            try:
                recognizer.read(modelo_path)
                recognizer.update(rostros, np.array(labels))
            except Exception:
                recognizer.train(rostros, np.array(labels))
        else:
            recognizer.train(rostros, np.array(labels))

        recognizer.save(modelo_path)
        print("MODELO LBPH ACTUALIZADO EXITOSAMENTE")

    # Zero-Knowledge: Cifrar foto de perfil con AES-256 y destruir capturas temporales
    personas_procesadas = set()
    for rostro_db in dataset:
        persona = rostro_db.persona
        if persona.id not in personas_procesadas and not persona.foto:
            if os.path.exists(rostro_db.imagen.path):
                try:
                    with open(rostro_db.imagen.path, 'rb') as f:
                        encrypted_bytes = encrypt_bytes(f.read())
                    filename = f"perfil_{persona.id}_{uuid.uuid4().hex[:6]}.jpg"
                    persona.foto.save(filename, ContentFile(encrypted_bytes), save=False)
                    personas_procesadas.add(persona.id)
                except Exception as e:
                    print(f"Error cifrando avatar: {e}")

        if not persona.biometria_facial:
            persona.biometria_facial = True
        persona.save()

        ruta = rostro_db.imagen.path
        if os.path.exists(ruta):
            try:
                os.remove(ruta)
            except Exception:
                pass

    dataset.delete()
    print("DATASET TEMPORAL DESTRUIDO (ZERO-KNOWLEDGE)")