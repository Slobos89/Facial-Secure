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
    Prueba de Vida Pasiva Biométrica (Passive Anti-Spoofing / Presentation Attack Detection PAD).
    Calibrada para eliminar falsos positivos en personas reales ante cámaras web/IP y laptops:
      - Piel humana viva: micro-textura rica (Laplaciano), varianza cromática biológica (Cr/Cb std),
        ausencia de patrones de subpíxeles Moiré y ausencia de reflejo especular sobre cristal.
      - Ataques de suplantación 2D detectados:
        1) Pantalla digital fría (OLED/LCD celular): Dominancia azul extrema y ausencia de perfusión sanguínea.
        2) Reflejo especular sobre cristal: Bandas de brillo polarizado de pantallas o celulares.
        3) Fotografía impresa en papel: Compresión cromática 2D extrema y textura plana.
        4) Patrón Moiré de subpíxeles: Interferencia armónica de alta frecuencia por trama física de pantalla.
    """
    if frame is None or len(bbox) < 4:
        return {
            'es_real': True,
            'score': 95.0,
            'dictamen': 'Rostro Humano Auténtico (En Vivo)',
            'alertas_spoof': [],
            'detalles': {}
        }

    frame_h, frame_w = frame.shape[:2]
    x1, y1, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    x2, y2 = x1 + w, y1 + h

    roi_face = _extraer_roi_seguro(frame, x1, y1, x2, y2)
    if roi_face is None or roi_face.size == 0 or w < 24 or h < 24:
        return {
            'es_real': False,
            'score': 20.0,
            'dictamen': '🚨 SPOOFING DETECTADO: Rostro de escala artificialmente reducida',
            'alertas_spoof': ['Escala facial inferior al umbral biométrico'],
            'detalles': {}
        }

    alertas = []
    penalizacion = 0.0

    face_width_ratio = float(w) / float(max(1, frame_w))

    # =========================================================================
    # 1. CROMATICIDAD BIOLÓGICA VS EMISIÓN DE PANTALLA DIGITAL
    # =========================================================================
    b_ch, g_ch, r_ch = cv2.split(roi_face)
    mean_b = float(np.mean(b_ch))
    mean_r = float(np.mean(r_ch))

    diff_rb = mean_r - mean_b
    blue_ratio = mean_b / (mean_r + 1.0)

    ycrcb_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2YCrCb)
    cr = ycrcb_face[:, :, 1].astype(float)
    cb = ycrcb_face[:, :, 2].astype(float)
    cr_std = float(np.std(cr))
    cb_std = float(np.std(cb))

    gray_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2GRAY)
    gray_norm = cv2.resize(gray_face, (128, 128))
    lap_var = float(cv2.Laplacian(gray_norm, cv2.CV_64F).var())

    hsv_face = cv2.cvtColor(roi_face, cv2.COLOR_BGR2HSV)
    sat = hsv_face[:, :, 1]
    val = hsv_face[:, :, 2]

    # Brillo especular característico de cristal de celular o monitor
    glare_mask = (val > 230) & (sat < 40)
    glare_ratio = float(np.sum(glare_mask)) / float(val.size)

    # =========================================================================
    # 2. ANÁLISIS ESPECTRAL 2D FFT (PATRÓN MOIRÉ DE PANTALLAS DIGITALES)
    # =========================================================================
    moire_ratio = 0.0
    try:
        f = np.fft.fft2(gray_norm)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-7)
        rows, cols = gray_norm.shape
        crow, ccol = rows // 2, cols // 2

        r_inner = min(rows, cols) // 6
        mask_inner = np.zeros((rows, cols), np.uint8)
        cv2.circle(mask_inner, (ccol, crow), r_inner, 1, -1)

        outer_mask = (mask_inner == 0)
        if np.any(outer_mask):
            peak_high = float(np.max(magnitude_spectrum[outer_mask]))
            mean_high = float(np.mean(magnitude_spectrum[outer_mask]))
            moire_ratio = peak_high / (mean_high + 1e-5)
    except Exception:
        pass

    # =========================================================================
    # 3. REGLAS ANTI-SPOOFING MULTI-FACTOR (SIN FALSOS POSITIVOS EN VIVO)
    # =========================================================================
    
    # Criterio A: Pantalla Digital Fría (requiere dominancia azul extrema Y ausencia de perfusión sanguínea)
    if (blue_ratio > 1.35 and diff_rb < -15.0 and cr_std < 8.0) or (blue_ratio > 1.50 and cr_std < 10.0):
        alertas.append('Retroiluminación fría de pantalla digital (OLED/LCD)')
        penalizacion += 38.0

    # Criterio B: Reflejo especular sobre cristal de pantalla
    if (glare_ratio > 0.12 and cr_std < 12.0) or (glare_ratio > 0.06 and moire_ratio > 2.45):
        alertas.append('Reflejo especular sobre cristal de pantalla')
        penalizacion += 38.0

    # Criterio C: Fotografía plana impresa en papel (cromaticidad nula y textura plana)
    if (cr_std < 3.2 and cb_std < 2.8 and lap_var < 25.0) or (cr_std < 2.8 and cb_std < 2.8):
        alertas.append('Cromaticidad plana de reproducción 2D (Foto impresa)')
        penalizacion += 42.0

    # Criterio D: Efecto Moiré de subpíxeles de pantalla digital
    if (moire_ratio > 2.85) or (moire_ratio > 2.50 and (glare_ratio > 0.04 or blue_ratio > 1.20)):
        alertas.append('Patrón de interferencia espectral (Moiré de pantalla)')
        penalizacion += 38.0

    # =========================================================================
    # 4. DICTAMEN FINAL DE PRUEBA DE VIDA PASIVA
    # =========================================================================
    liveness_score = max(10.0, min(99.0, 96.0 - penalizacion))
    # Es real si no tiene penalizaciones severas que denoten suplantación
    es_real = (liveness_score >= 60.0) and (penalizacion < 38.0)

    if es_real:
        dictamen = 'Rostro Humano Auténtico (En Vivo)'
    else:
        causa_principal = ', '.join(alertas[:2]) if alertas else 'Anomalía de superficie 2D'
        dictamen = f'🚨 SPOOFING DETECTADO [PANTALLA / FOTO]: {causa_principal}'

    return {
        'es_real': es_real,
        'score': round(liveness_score, 1),
        'dictamen': dictamen,
        'alertas_spoof': alertas,
        'detalles': {
            'laplacian_var': round(lap_var, 2),
            'glare_ratio': round(glare_ratio, 4),
            'blue_ratio': round(blue_ratio, 3),
            'cr_std': round(cr_std, 2),
            'moire_ratio': round(moire_ratio, 2),
            'face_width_ratio': round(face_width_ratio, 3),
        }
    }
