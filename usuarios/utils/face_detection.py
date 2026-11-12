import cv2
import numpy as np
from PIL import Image
from usuarios.utils.deep_learning import DeepFaceEngine


def detectar_y_recortar_rostro(image_pil):
    """
    Detecta el rostro principal en una imagen PIL usando el motor Deep Learning
    OpenCV YuNet (DeepFaceEngine) y recorta la región facial con margen.
    Si no detecta un rostro frontal estricto, aplica un recorte central de respaldo.
    """
    if image_pil.mode != 'RGB':
        image_pil = image_pil.convert('RGB')

    image_np = np.array(image_pil)
    image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

    faces = []
    try:
        engine = DeepFaceEngine.get_instance()
        faces = engine.detect_faces(image_bgr)
    except Exception as e:
        print('Aviso YuNet en detectar_y_recortar_rostro:', e)

    if faces is None or len(faces) == 0:
        # Fallback: Recorte central 70%
        w_img, h_img = image_pil.size
        cx, cy = w_img // 2, h_img // 2
        crop_size = min(w_img, h_img) * 0.7
        x1 = max(0, int(cx - crop_size / 2))
        y1 = max(0, int(cy - crop_size / 2))
        x2 = min(w_img, int(cx + crop_size / 2))
        y2 = min(h_img, int(cy + crop_size / 2))
        rostro = image_pil.crop((x1, y1, x2, y2))
        return rostro.resize((200, 200))

    # Seleccionar el rostro más grande / dominante
    best_face = max(faces, key=lambda f: float(f[2]) * float(f[3]))
    x, y, w, h = int(best_face[0]), int(best_face[1]), int(best_face[2]), int(best_face[3])

    padding_x = int(w * 0.25)
    padding_y = int(h * 0.35)

    x1 = max(0, x - padding_x)
    y1 = max(0, y - padding_y)
    x2 = min(image_pil.width, x + w + padding_x)
    y2 = min(image_pil.height, y + h + padding_y)

    if x2 <= x1 or y2 <= y1:
        return image_pil.resize((200, 200))

    rostro = image_pil.crop((x1, y1, x2, y2))
    return rostro.resize((200, 200))
