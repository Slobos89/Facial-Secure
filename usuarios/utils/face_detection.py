import cv2
import numpy as np
from PIL import Image

def detectar_y_recortar_rostro(image_pil):
    """
    Detecta el rostro principal en una imagen PIL usando OpenCV Haar Cascades
    con múltiples pasadas de sensibilidad y selección del rostro dominante.
    """
    image_np = np.array(image_pil)

    if len(image_np.shape) == 2:
        gray = image_np
    elif image_np.shape[2] == 4:
        image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGBA2BGR)
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    # 1. Pasada estándar
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(40, 40)
    )

    # 2. Pasada de alta sensibilidad si no se detectó
    if len(faces) == 0:
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=2,
            minSize=(30, 30)
        )

    # 3. Pasada con cascade alt2 si aún no se detecta
    if len(faces) == 0:
        alt_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml')
        faces = alt_cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=2, minSize=(30, 30))

    if len(faces) == 0:
        # Fallback: Recorte central 60%
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
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])

    padding_x = int(w * 0.25)
    padding_y = int(h * 0.35)

    x1 = max(0, x - padding_x)
    y1 = max(0, y - padding_y)
    x2 = min(image_pil.width, x + w + padding_x)
    y2 = min(image_pil.height, y + h + padding_y)

    rostro = image_pil.crop((x1, y1, x2, y2))
    return rostro.resize((200, 200))