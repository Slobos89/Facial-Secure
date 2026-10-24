import os
import cv2
import numpy as np
from usuarios.models import RostroCapturado, Persona
from usuarios.utils.security import decrypt_bytes
from usuarios.utils.deep_learning import DeepFaceEngine


def entrenar_modelo():
    """
    Entrenamiento / Actualización de Embeddings Deep Learning (Zero-Knowledge):
    1. Carga las capturas temporales recién registradas (RostroCapturado).
    2. Extrae y promedia los vectores Deep Learning (SFace + YuNet 5-landmarks) para cada persona.
    3. Guarda el vector L2 normalizado de 128 dimensiones en `persona.embedding_facial`.
    4. Destruye y borra permanentemente todas las capturas temporales crudas del disco y la BD.
    """
    dataset = RostroCapturado.objects.select_related('persona').all()
    if not dataset.exists():
        return

    engine = DeepFaceEngine.get_instance()
    
    # Agrupar capturas por persona
    capturas_por_persona = {}
    for rostro_db in dataset:
        p_id = rostro_db.persona_id
        if p_id not in capturas_por_persona:
            capturas_por_persona[p_id] = []
        capturas_por_persona[p_id].append(rostro_db)

    for persona_id, capturas in capturas_por_persona.items():
        persona = capturas[0].persona
        features_list = []

        for c in capturas:
            try:
                ruta = c.imagen.path
                if os.path.exists(ruta):
                    img = cv2.imread(ruta)
                    if img is not None:
                        _, feat = engine.extract_embedding_from_image(img)
                        if feat is not None:
                            features_list.append(feat)
            except Exception as e:
                print(f"Error procesando captura {c.id} para embedding: {e}")

        if len(features_list) > 0:
            # Vector centroide promediado y re-normalizado
            centroid = np.mean(features_list, axis=0)
            centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-7)
            persona.embedding_facial = centroid_norm.tolist()
            persona.biometria_facial = True
            persona.save(update_fields=['embedding_facial', 'biometria_facial'])
            print(f"EMBEDDING DEEP LEARNING ACTUALIZADO PARA: {persona.nombre} {persona.apellido} ({len(features_list)} muestras)")

    # Zero-Knowledge: Destrucción total de capturas temporales crudas
    for rostro_db in dataset:
        if hasattr(rostro_db.imagen, 'path') and os.path.exists(rostro_db.imagen.path):
            try:
                os.remove(rostro_db.imagen.path)
            except Exception:
                pass

    dataset.delete()
    print("DATASET TEMPORAL DESTRUIDO (ZERO-KNOWLEDGE)")