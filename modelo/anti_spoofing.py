import cv2
import numpy as np


def _extraer_roi_seguro(frame, x1, y1, x2, y2):
    """Extrae región asegurando que esté dentro de los límites del cuadro."""
    h, w = frame.shape[:2]
    x1_c = max(0, min(w - 1, int(x1)))
    y1_c = max(0, min(h - 1, int(y1)))
    x2_c = max(0, min(w, int(x2)))
    y2_c = max(0, min(h, int(y2)))
    if x2_c <= x1_c or y2_c <= y1_c:
        return None
    return frame[y1_c:y2_c, x1_c:x2_c]


def verificar_prueba_de_vida(frame, bbox):
    """
    Prueba de Vida Pasiva (Passive Anti-Spoofing / Liveness Detection).
    Evalúa si el rostro capturado corresponde a un ser humano tridimensional en vivo,
    o a un intento de suplantación mediante:
    1. Pantalla digital de smartphone / tablet / monitor (efecto Moiré, backlight, gamut digital).
    2. Fotografía impresa en papel (pérdida de microtextura, superficie plana 2D).
    3. Bordes o biseles de teléfono móvil rodeando el rostro.
    4. Reflejo especular plano de cristal de pantalla.

    Retorna un diccionario estructurado con:
    - es_real: bool (True si es humano real, False si es spoofing)
    - score: float (0.0 a 100.0)
    - dictamen: str
    - alertas_spoof: list de motivos detectados
    """
    if frame is None or len(bbox) < 4:
        return {
            'es_real': True,
            'score': 85.0,
            'dictamen': 'Rostro no analizable',
            'alertas_spoof': [],
            'detalles': {}
        }

    x1, y1, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    x2, y2 = x1 + w, y1 + h

    roi_face = _extraer_roi_seguro(frame, x1, y1, x2, y2)
    if roi_face is None or roi_face.size == 0 or w < 30 or h < 30:
        return {
            'es_real': True,
            'score': 80.0,
            'dictamen': 'Rostro muy pequeño para análisis pasivo',
            'alertas_spoof': [],
            'detalles': {}
        }

    alertas = []
    penalizacion = 0.0

    # 1. ANÁLISIS DE MICROTEXTURA Y GRADIENTES (LAPLACIANO)
    gray_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2GRAY)
    lap_var = cv2.Laplacian(gray_face, cv2.CV_64F).var()

    # Si la varianza es extremadamente baja (< 15.0), es una foto impresa borrosa o superficie plana 2D
    if lap_var < 15.0:
        alertas.append('Superficie plana / Falta de microtextura tridimensional (Foto Impresa)')
        penalizacion += 40.0

    # 2. ANÁLISIS DE ESPECTRO DE FRECUENCIA 2D (FFT) PARA MOIRÉ DIGITAL
    try:
        f = np.fft.fft2(gray_face)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-7)
        rows, cols = gray_face.shape
        crow, ccol = rows // 2, cols // 2
        
        r_inner = min(rows, cols) // 5
        mask_inner = np.zeros((rows, cols), np.uint8)
        cv2.circle(mask_inner, (ccol, crow), r_inner, 1, -1)
        
        outer_mask = (mask_inner == 0)
        if np.any(outer_mask):
            peak_high = np.max(magnitude_spectrum[outer_mask])
            mean_high = np.mean(magnitude_spectrum[outer_mask])
            moire_ratio = peak_high / (mean_high + 1e-5)
            # Moiré de pantalla produce picos espectrales armónicos concentrados
            if moire_ratio > 2.6 and lap_var > 1800.0:
                alertas.append('Patrón de interferencia / Rejilla de píxeles LCD (Efecto Moiré)')
                penalizacion += 35.0
    except Exception:
        pass

    # 3. ANÁLISIS CROMÁTICO Y RETROILUMINACIÓN (YCrCb & HSV)
    ycrcb_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2YCrCb)
    cr = ycrcb_face[:, :, 1].astype(float)
    cb = ycrcb_face[:, :, 2].astype(float)
    hsv_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2HSV)
    sat = hsv_face[:, :, 1]
    val = hsv_face[:, :, 2]

    # Varianza de croma: la piel viva natural tiene variación cromática por vascularización.
    # Las fotos en papel económico muestran croma anormalmente plano.
    cr_std = np.std(cr)
    cb_std = np.std(cb)
    if cr_std < 2.5 and cb_std < 2.5 and lap_var < 45.0:
        alertas.append('Cromaticidad artificialmente plana (Impresión 2D)')
        penalizacion += 35.0

    # Detección de retroiluminación LED/LCD (píxeles con saturación extrema no biológica)
    sat_extrema = np.sum(sat > 235) / sat.size
    if sat_extrema > 0.18:
        alertas.append('Gama cromática sobresaturada (Retroiluminación de Pantalla)')
        penalizacion += 30.0

    # 4. REFLEJO ESPECULAR DE CRISTAL / PANTALLA
    # Las pantallas de cristal de smartphones producen zonas de brillo plano especular (V > 250, S < 18)
    glare_mask = (val > 248) & (sat < 20)
    glare_ratio = np.sum(glare_mask) / val.size
    if glare_ratio > 0.08:
        alertas.append('Reflejo especular plano de cristal (Pantalla de Teléfono / Dispositivo)')
        penalizacion += 40.0

    # 5. DETECCIÓN DE BORDES DE BISEL / CELULAR ALREDEDOR DEL ROSTRO
    margen_x = int(w * 0.20)
    margen_y = int(h * 0.20)
    roi_exterior = _extraer_roi_seguro(frame, x1 - margen_x, y1 - margen_y, x2 + margen_x, y2 + margen_y)
    borde_telefono_detectado = False
    if roi_exterior is not None and roi_exterior.size > 0:
        gray_ext = cv2.cvtColor(roi_exterior, cv2.COLOR_BGR2GRAY)
        canny = cv2.Canny(gray_ext, 80, 200)
        lines = cv2.HoughLinesP(canny, 1, np.pi / 180, threshold=80, minLineLength=int(min(w, h) * 0.8), maxLineGap=8)
        if lines is not None and len(lines) >= 4:
            lineas_rectas = 0
            for line in lines:
                coords = line.flatten()
                if len(coords) < 4:
                    continue
                lx1, ly1, lx2, ly2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                dx = abs(lx2 - lx1)
                dy = abs(ly2 - ly1)
                if dx < 3 or dy < 3:
                    lineas_rectas += 1
            if lineas_rectas >= 3:
                borde_telefono_detectado = True
                alertas.append('Borde recto de pantalla de smartphone / soporte detectado')
                penalizacion += 30.0

    # CÁLCULO DEL SCORE FINAL
    liveness_score = max(5.0, min(100.0, 95.0 - penalizacion))
    es_real = (liveness_score >= 55.0) and (len(alertas) == 0 or (len(alertas) == 1 and penalizacion <= 30.0))

    if es_real:
        dictamen = 'Rostro Auténtico (En Vivo)'
    else:
        dictamen = f"🚨 SPOOFING DETECTADO [PANTALLA / FOTO]: {', '.join(alertas)}"

    return {
        'es_real': es_real,
        'score': round(liveness_score, 1),
        'dictamen': dictamen,
        'alertas_spoof': alertas,
        'detalles': {
            'laplacian_var': round(float(lap_var), 2),
            'glare_ratio': round(float(glare_ratio), 4),
            'borde_marco': borde_telefono_detectado
        }
    }
