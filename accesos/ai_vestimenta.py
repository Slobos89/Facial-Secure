import os
import cv2
import numpy as np


# Paleta de referencia para clasificación cromática en español
PALETA_COLORES = [
    {'nombre': 'Negro', 'rgb': (20, 20, 25), 'hex': '#1e293b'},
    {'nombre': 'Blanco', 'rgb': (240, 240, 245), 'hex': '#f8fafc'},
    {'nombre': 'Gris Oscuro', 'rgb': (75, 85, 99), 'hex': '#4b5563'},
    {'nombre': 'Gris Claro', 'rgb': (156, 163, 175), 'hex': '#9ca3af'},
    {'nombre': 'Azul Marino', 'rgb': (28, 56, 121), 'hex': '#1e3a8a'},
    {'nombre': 'Azul / Denim', 'rgb': (37, 99, 235), 'hex': '#2563eb'},
    {'nombre': 'Celeste', 'rgb': (125, 211, 252), 'hex': '#38bdf8'},
    {'nombre': 'Rojo', 'rgb': (220, 38, 38), 'hex': '#dc2626'},
    {'nombre': 'Granate / Burdeo', 'rgb': (136, 19, 55), 'hex': '#881337'},
    {'nombre': 'Verde Oscuro', 'rgb': (22, 101, 52), 'hex': '#166534'},
    {'nombre': 'Verde Oliva / Militar', 'rgb': (77, 100, 45), 'hex': '#4d642d'},
    {'nombre': 'Amarillo', 'rgb': (234, 179, 8), 'hex': '#eab308'},
    {'nombre': 'Naranja', 'rgb': (234, 88, 12), 'hex': '#ea580c'},
    {'nombre': 'Café / Marrón', 'rgb': (120, 53, 15), 'hex': '#78350f'},
    {'nombre': 'Beige / Caqui', 'rgb': (214, 194, 160), 'hex': '#d6c2a0'},
    {'nombre': 'Morado / Violeta', 'rgb': (126, 34, 206), 'hex': '#7e22ce'},
]


def _cargar_imagen(img_or_path):
    """Carga imagen desde ruta, objeto de Django ImageField o numpy array."""
    if img_or_path is None:
        return None
    if isinstance(img_or_path, np.ndarray):
        return img_or_path
    
    # Si es un FieldFile de Django o archivo
    path = getattr(img_or_path, 'path', None)
    if not path and isinstance(img_or_path, str):
        path = img_or_path
        
    if path and os.path.exists(path):
        img = cv2.imread(path)
        return img
    
    # Intentar leer desde buffer en memoria
    try:
        if hasattr(img_or_path, 'read'):
            img_or_path.seek(0)
            bytes_data = img_or_path.read()
            nparr = np.frombuffer(bytes_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
    except Exception:
        pass
    return None


def _clasificar_color_rgb(r, g, b):
    """Encuentra el nombre del color más cercano en el espacio RGB ponderado."""
    mejor_dist = float('inf')
    mejor_color = PALETA_COLORES[0]
    for col in PALETA_COLORES:
        cr, cg, cb = col['rgb']
        # Distancia euclídea con pesos perceptuales CIE
        dist = 0.3 * (r - cr) ** 2 + 0.59 * (g - cg) ** 2 + 0.11 * (b - cb) ** 2
        if dist < mejor_dist:
            mejor_dist = dist
            mejor_color = col
    return mejor_color


def _obtener_color_dominante_roi(roi):
    """Extrae el color predominante de una región de interés mediante K-Means."""
    if roi is None or roi.size == 0:
        return {'nombre': 'No determinado', 'rgb': (128, 128, 128), 'hex': '#808080'}
    
    # Redimensionar para análisis rápido
    peq = cv2.resize(roi, (60, 60))
    pixels = peq.reshape((-1, 3)).astype(np.float32)

    # 3 clusters K-Means
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(pixels, 3, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    # Contar frecuencias de cada cluster
    counts = np.bincount(labels.flatten())
    # Tomar el centro más frecuente
    idx_max = np.argmax(counts)
    b_dom, g_dom, r_dom = centers[idx_max]
    
    return _clasificar_color_rgb(int(r_dom), int(g_dom), int(b_dom))


def _extraer_histograma_hsv(roi):
    """Calcula histograma normalizado Hue-Saturation de una región de vestimenta."""
    if roi is None or roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # 24 bins de matiz (Hue), 16 de saturación
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 20, 256])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist


def analizar_vestimenta_individual(img_or_path):
    """
    Analiza una sola fotografía y deduce el color predominante superior e inferior.
    """
    img = _cargar_imagen(img_or_path)
    if img is None:
        return {
            'exito': False,
            'color_superior': 'No disponible',
            'hex_superior': '#64748b',
            'color_inferior': 'No disponible',
            'hex_inferior': '#64748b',
            'resumen': 'Sin imagen disponible para análisis.'
        }

    h, w = img.shape[:2]
    # Región Torso Superior (aprox 18% a 55% de altura central)
    y_sup_ini, y_sup_fin = int(h * 0.18), int(h * 0.55)
    x_sup_ini, x_sup_fin = int(w * 0.20), int(w * 0.80)
    roi_superior = img[y_sup_ini:y_sup_fin, x_sup_ini:x_sup_fin]

    # Región Inferior (aprox 55% a 92% de altura)
    y_inf_ini, y_inf_fin = int(h * 0.55), int(h * 0.92)
    x_inf_ini, x_inf_fin = int(w * 0.22), int(w * 0.78)
    roi_inferior = img[y_inf_ini:y_inf_fin, x_inf_ini:x_inf_fin]

    col_sup = _obtener_color_dominante_roi(roi_superior)
    col_inf = _obtener_color_dominante_roi(roi_inferior)

    resumen = f"Atuendo detectado: Prenda superior {col_sup['nombre']}, prenda inferior {col_inf['nombre']}."

    return {
        'exito': True,
        'color_superior': col_sup['nombre'],
        'hex_superior': col_sup['hex'],
        'color_inferior': col_inf['nombre'],
        'hex_inferior': col_inf['hex'],
        'resumen': resumen
    }


def comparar_vestimentas(img_ingreso, img_egreso):
    """
    Compara mediante visión computacional la vestimenta registrada al ingreso
    versus la vestimenta capturada al egreso.
    Calcula similitud cromática en torso superior e inferior, y genera dictamen.
    """
    im1 = _cargar_imagen(img_ingreso)
    im2 = _cargar_imagen(img_egreso)

    if im1 is None or im2 is None:
        return {
            'exito': False,
            'similitud_global': 0.0,
            'coincidencia_superior': 0.0,
            'coincidencia_inferior': 0.0,
            'alerta_vestimenta': False,
            'dictamen': 'No se cuenta con imágenes válidas de ingreso y egreso para comparar.'
        }

    # Redimensionar ambas imágenes al mismo tamaño estándar para comparación equitativa
    target_size = (320, 480)
    im1_norm = cv2.resize(im1, target_size)
    im2_norm = cv2.resize(im2, target_size)

    h, w = 480, 320
    # Región superior (torso)
    roi1_sup = im1_norm[int(h * 0.18):int(h * 0.55), int(w * 0.18):int(w * 0.82)]
    roi2_sup = im2_norm[int(h * 0.18):int(h * 0.55), int(w * 0.18):int(w * 0.82)]

    # Región inferior (pantalón)
    roi1_inf = im1_norm[int(h * 0.55):int(h * 0.92), int(w * 0.20):int(w * 0.80)]
    roi2_inf = im2_norm[int(h * 0.55):int(h * 0.92), int(w * 0.20):int(w * 0.80)]

    # Colores dominantes
    col1_sup = _obtener_color_dominante_roi(roi1_sup)
    col2_sup = _obtener_color_dominante_roi(roi2_sup)
    col1_inf = _obtener_color_dominante_roi(roi1_inf)
    col2_inf = _obtener_color_dominante_roi(roi2_inf)

    # Histogramas HSV
    hist1_sup = _extraer_histograma_hsv(roi1_sup)
    hist2_sup = _extraer_histograma_hsv(roi2_sup)
    hist1_inf = _extraer_histograma_hsv(roi1_inf)
    hist2_inf = _extraer_histograma_hsv(roi2_inf)

    # Cálculo métrico superior
    if hist1_sup is not None and hist2_sup is not None:
        correl_sup = cv2.compareHist(hist1_sup, hist2_sup, cv2.HISTCMP_CORREL)
        bhatt_sup = cv2.compareHist(hist1_sup, hist2_sup, cv2.HISTCMP_BHATTACHARYYA)
        # Normalizar a 0-100
        sim_sup = max(0.0, min(100.0, ((correl_sup + 1.0) / 2.0 * 0.60 + (1.0 - bhatt_sup) * 0.40) * 100.0))
    else:
        sim_sup = 50.0

    # Bono o penalización por color dominante idéntico
    if col1_sup['nombre'] == col2_sup['nombre']:
        sim_sup = min(100.0, sim_sup * 1.08)
    else:
        sim_sup = max(10.0, sim_sup * 0.75)

    # Cálculo métrico inferior
    if hist1_inf is not None and hist2_inf is not None:
        correl_inf = cv2.compareHist(hist1_inf, hist2_inf, cv2.HISTCMP_CORREL)
        bhatt_inf = cv2.compareHist(hist1_inf, hist2_inf, cv2.HISTCMP_BHATTACHARYYA)
        sim_inf = max(0.0, min(100.0, ((correl_inf + 1.0) / 2.0 * 0.60 + (1.0 - bhatt_inf) * 0.40) * 100.0))
    else:
        sim_inf = 50.0

    if col1_inf['nombre'] == col2_inf['nombre']:
        sim_inf = min(100.0, sim_inf * 1.08)
    else:
        sim_inf = max(10.0, sim_inf * 0.75)

    similitud_global = round((sim_sup * 0.55 + sim_inf * 0.45), 1)
    sim_sup = round(sim_sup, 1)
    sim_inf = round(sim_inf, 1)

    # Umbral de seguridad para cambio de vestimenta: 70%
    es_alerta = similitud_global < 70.0

    if not es_alerta:
        dictamen = (
            f"✅ VESTIMENTA CONFORME ({similitud_global}% coincidencia): El visitante egresa con el mismo atuendo "
            f"registrado al ingreso (Superior: {col1_sup['nombre']} vs {col2_sup['nombre']}; "
            f"Inferior: {col1_inf['nombre']} vs {col2_inf['nombre']}). Sin indicios de intercambio de ropa."
        )
    else:
        dictamen = (
            f"🚨 ALERTA CRÍTICA DE VESTIMENTA ({similitud_global}% coincidencia): Discrepancia sustancial entre la ropa "
            f"de ingreso ({col1_sup['nombre']} / {col1_inf['nombre']}) y egreso ({col2_sup['nombre']} / {col2_inf['nombre']}). "
            f"Posible suplantación o intento de salida de un interno con ropa de civil."
        )

    return {
        'exito': True,
        'similitud_global': similitud_global,
        'coincidencia_superior': sim_sup,
        'coincidencia_inferior': sim_inf,
        'alerta_vestimenta': es_alerta,
        'color_ingreso_sup': col1_sup['nombre'],
        'color_egreso_sup': col2_sup['nombre'],
        'color_ingreso_inf': col1_inf['nombre'],
        'color_egreso_inf': col2_inf['nombre'],
        'dictamen': dictamen
    }
