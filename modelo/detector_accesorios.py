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


def _calcular_porcentaje_piel(roi_bgr):
    """Calcula el porcentaje de píxeles compatibles con tono de piel humana en YCrCb."""
    if roi_bgr is None or roi_bgr.size == 0:
        return 0.0
    ycrcb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2YCrCb)
    # Rango estándar perceptual de piel humana
    lower_skin = np.array([0, 133, 77], dtype=np.uint8)
    upper_skin = np.array([255, 173, 127], dtype=np.uint8)
    mask = cv2.inRange(ycrcb, lower_skin, upper_skin)
    total_pixels = mask.size
    skin_pixels = cv2.countNonZero(mask)
    return (skin_pixels / total_pixels) * 100.0


def detectar_accesorios_prohibidos(frame, bbox, landmarks=None):
    """
    Detecta en tiempo real si el sujeto porta accesorios que oculten sus rasgos:
    1. Lentes de sol u oscuros (Sunglasses).
    2. Gorro, jockey o capucha (Hats/Caps/Hoods).
    3. Mascarilla o tapabocas (Facial masks).

    Retorna un diccionario estructurado con los hallazgos y alertas.
    """
    if frame is None or len(bbox) < 4:
        return {
            'lentes_oscuros': False,
            'gorro': False,
            'mascarilla': False,
            'rostro_despejado': True,
            'accesorios': [],
            'mensaje_alerta': ''
        }

    x1, y1, w, h = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    x2, y2 = x1 + w, y1 + h

    accesorios = []

    # 1. DETECCIÓN DE LENTES OSCUROS / DE SOL
    # Región de los ojos: franja entre 22% y 48% de la altura de la cara
    y_ojo_ini = y1 + int(h * 0.22)
    y_ojo_fin = y1 + int(h * 0.48)
    x_ojo_ini = x1 + int(w * 0.15)
    x_ojo_fin = x2 - int(w * 0.15)
    roi_ojos = _extraer_roi_seguro(frame, x_ojo_ini, y_ojo_ini, x_ojo_fin, y_ojo_fin)

    lentes_oscuros = False
    if roi_ojos is not None and roi_ojos.size > 0:
        hsv_ojos = cv2.cvtColor(roi_ojos, cv2.COLOR_BGR2HSV)
        val_canal = hsv_ojos[:, :, 2] # Brillo (Value)
        media_brillo = np.mean(val_canal)
        # Porcentaje de píxeles muy oscuros (lentes oscuros absorben luz)
        pixeles_oscuros = np.sum(val_canal < 50) / val_canal.size
        porc_piel_ojos = _calcular_porcentaje_piel(roi_ojos)

        # Si el área ocular es excesivamente oscura y tiene poca piel visible -> Lentes de sol
        if (media_brillo < 68 and pixeles_oscuros > 0.42) or (pixeles_oscuros > 0.65 and porc_piel_ojos < 20.0):
            lentes_oscuros = True
            accesorios.append('Lentes Oscuros')

    # 2. DETECCIÓN DE GORRO / JOCKEY / CAPUCHA
    # Región superior: desde por encima de la frente hasta la parte alta del rostro
    y_gorro_ini = y1 - int(h * 0.18)
    y_gorro_fin = y1 + int(h * 0.15)
    roi_frente = _extraer_roi_seguro(frame, x1 + int(w * 0.10), y_gorro_ini, x2 - int(w * 0.10), y_gorro_fin)

    gorro = False
    if roi_frente is not None and roi_frente.size > 0:
        porc_piel_frente = _calcular_porcentaje_piel(roi_frente)
        # Analizar uniformidad y textura de tela en la frente/cabeza
        gris_frente = cv2.cvtColor(roi_frente, cv2.COLOR_BGR2GRAY)
        varianza_laplace = cv2.Laplacian(gris_frente, cv2.CV_64F).var()
        media_frente = np.mean(gris_frente)

        # Si hay visera o prenda oscura cubriendo la frente y muy poca piel visible
        if (porc_piel_frente < 12.0 and media_frente < 75) or (porc_piel_frente < 8.0 and varianza_laplace > 80):
            gorro = True
            accesorios.append('Gorro / Capucha')

    # 3. DETECCIÓN DE MASCARILLA / TAPABOCAS
    # Región inferior: desde debajo de la nariz (52% altura) hasta la barbilla (95% altura)
    y_boca_ini = y1 + int(h * 0.52)
    y_boca_fin = y1 + int(h * 0.95)
    roi_boca = _extraer_roi_seguro(frame, x1 + int(w * 0.15), y_boca_ini, x2 - int(w * 0.15), y_boca_fin)

    mascarilla = False
    if roi_boca is not None and roi_boca.size > 0:
        porc_piel_boca = _calcular_porcentaje_piel(roi_boca)
        hsv_boca = cv2.cvtColor(roi_boca, cv2.COLOR_BGR2HSV)
        sat_canal = hsv_boca[:, :, 1]
        val_boca = hsv_boca[:, :, 2]

        # Si el área de boca/mentón tiene menos del 18% de tono de piel y presenta un color dominante (blanco, azul, negro quirúrgico)
        es_blanca_o_azul = (np.mean(val_boca) > 175 and np.mean(sat_canal) < 55) or (np.mean(hsv_boca[:, :, 0]) > 95 and np.mean(hsv_boca[:, :, 0]) < 125)
        es_oscura_solida = np.mean(val_boca) < 45

        if (porc_piel_boca < 18.0) and (es_blanca_o_azul or es_oscura_solida or porc_piel_boca < 8.0):
            mascarilla = True
            accesorios.append('Mascarilla')

    rostro_despejado = len(accesorios) == 0

    if not rostro_despejado:
        mensaje_alerta = f"⚠️ RETIRAR: {', '.join(accesorios).upper()} PARA VALIDACIÓN"
    else:
        mensaje_alerta = "✅ Rostro Despejado"

    return {
        'lentes_oscuros': lentes_oscuros,
        'gorro': gorro,
        'mascarilla': mascarilla,
        'rostro_despejado': rostro_despejado,
        'accesorios': accesorios,
        'mensaje_alerta': mensaje_alerta
    }
