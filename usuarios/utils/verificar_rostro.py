import cv2
import os
import numpy as np
from usuarios.models import Persona
from usuarios.utils.deep_learning import DeepFaceEngine


def reconocer_rostro(imagen_path):
    """
    Reconoce el rostro en una imagen dada utilizando Deep Learning (SFace + YuNet).
    Retorna {'persona': Persona, 'confianza': porcentaje} o None si no hay coincidencia válida.
    """
    if not os.path.exists(imagen_path):
        return None

    img = cv2.imread(imagen_path)
    if img is None:
        return None

    engine = DeepFaceEngine.get_instance()
    aligned, feat = engine.extract_embedding_from_image(img)
    if feat is None:
        return None

    personas = list(
        Persona.objects.filter(biometria_facial=True)
        .exclude(embedding_facial__isnull=True)
    )
    if not personas:
        return None

    matrix = np.array([p.embedding_facial for p in personas], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-7
    matrix = matrix / norms

    best_persona, score, porcentaje = engine.match_against_matrix(feat, matrix, personas)

    if porcentaje >= 50.0 and best_persona is not None:
        return {
            'persona': best_persona,
            'confianza': int(porcentaje)
        }

    return None