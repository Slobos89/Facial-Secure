import cv2
import numpy as np
from PIL import Image


def detectar_y_recortar_rostro(image_pil):

    image_np = np.array(image_pil)

    image_bgr = cv2.cvtColor(
        image_np,
        cv2.COLOR_RGB2BGR
    )

    gray = cv2.cvtColor(
        image_bgr,
        cv2.COLOR_BGR2GRAY
    )

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades +
        'haarcascade_frontalface_default.xml'
    )

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=3,
        minSize=(50, 50)
    )

    if len(faces) == 0:
        return None

    x, y, w, h = faces[0]

    padding_x = int(w * 0.25)

    padding_y = int(h * 0.35)


    x1 = max(0, x - padding_x)

    y1 = max(0, y - padding_y)

    x2 = min(
        image_pil.width,
        x + w + padding_x
    )

    y2 = min(
        image_pil.height,
        y + h + padding_y
    )


    rostro = image_pil.crop(

        (x1, y1, x2, y2)

    )

    rostro = rostro.resize((300,300))

    return rostro