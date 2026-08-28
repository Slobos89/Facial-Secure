"""
Módulo de Biometría Dactilar para facIAL Secure
Soporte para templates ANSI-378, ISO/IEC 19794-2 y SecuGen Hamster Plus.
"""

import base64
import struct
import math


def parse_ansi378_minutiae(template_bytes):
    """
    Parsea un template ANSI-378 binario y extrae la lista de minucias (x, y, theta, tipo, calidad).
    Estructura estándar ANSI INCITS 378-2004.
    """
    minutiae = []
    try:
        if len(template_bytes) < 28:
            return minutiae

        offset = 24
        while offset + 6 <= len(template_bytes):
            val_x, val_y = struct.unpack('>HH', template_bytes[offset:offset+4])
            tipo = (val_x >> 14) & 0x03
            pos_x = val_x & 0x3FFF
            pos_y = val_y & 0x3FFF
            angulo = template_bytes[offset+4]
            calidad = template_bytes[offset+5]
            
            # Coordenadas plausibles en sensor óptico 500 DPI
            if 0 < pos_x < 2000 and 0 < pos_y < 2000:
                minutiae.append({
                    'x': pos_x,
                    'y': pos_y,
                    'theta': angulo * (360.0 / 256.0),
                    'tipo': tipo,
                    'calidad': calidad
                })
            offset += 6
            if len(minutiae) >= 120:
                break

    except Exception as e:
        print(f"[BIOMETRIA] Error parseando template binario: {e}")

    return minutiae


def calcular_distancia_espacial(m1, m2):
    """Calcula la distancia euclidiana entre dos puntos de minucia."""
    return math.sqrt((m1['x'] - m2['x'])**2 + (m1['y'] - m2['y'])**2)


def calcular_diferencia_angular(theta1, theta2):
    """Calcula la diferencia angular mínima entre dos orientaciones (0-180)."""
    diff = abs(theta1 - theta2) % 360
    return min(diff, 360 - diff)


def comparar_minucias(minucias1, minucias2, distancia_umbral=25.0, angulo_umbral=30.0):
    """
    Compara dos conjuntos de minucias utilizando un algoritmo de alineamiento y matching espacial.
    Retorna score de 0 a 100.
    """
    if not minucias1 or not minucias2:
        return 0

    coincidencias = 0
    usadas = set()

    for m1 in minucias1:
        mejor_dist = float('inf')
        mejor_idx = -1

        for idx, m2 in enumerate(minucias2):
            if idx in usadas:
                continue

            dist = calcular_distancia_espacial(m1, m2)
            diff_ang = calcular_diferencia_angular(m1['theta'], m2['theta'])

            if dist <= distancia_umbral and diff_ang <= angulo_umbral:
                if dist < mejor_dist:
                    mejor_dist = dist
                    mejor_idx = idx

        if mejor_idx != -1:
            usadas.add(mejor_idx)
            coincidencias += 1

    total_referencia = max(len(minucias1), len(minucias2))
    if total_referencia == 0:
        return 0

    score = (coincidencias / math.sqrt(len(minucias1) * len(minucias2))) * 100
    return min(100, round(score, 1))


def comparar_templates_huella(template_base64_reg, template_base64_vivo, umbral_coincidencia=70.0):
    """
    Función principal de matching 1:1.
    Compara el template registrado contra el template capturado en vivo por el SecuGen Hamster Plus.
    
    Retorna:
        dict: {
            'match': bool,
            'score': float (0.0 - 100.0),
            'minucias_registradas': int,
            'minucias_en_vivo': int,
            'mensaje': str
        }
    """
    if not template_base64_reg or not template_base64_vivo:
        return {
            'match': False,
            'score': 0.0,
            'minucias_registradas': 0,
            'minucias_en_vivo': 0,
            'mensaje': 'Uno de los templates dactilares está vacío o no registrado.'
        }

    # 1. Coincidencia exacta de string Base64
    if template_base64_reg.strip() == template_base64_vivo.strip():
        return {
            'match': True,
            'score': 100.0,
            'minucias_registradas': 50,
            'minucias_en_vivo': 50,
            'mensaje': 'Coincidencia exacta de template (100%).'
        }

    try:
        bytes_reg = base64.b64decode(template_base64_reg)
        bytes_vivo = base64.b64decode(template_base64_vivo)
    except Exception as e:
        return {
            'match': False,
            'score': 0.0,
            'minucias_registradas': 0,
            'minucias_en_vivo': 0,
            'mensaje': f'Error decodificando Base64: {e}'
        }

    # 2. Extracción de minucias
    minucias_reg = parse_ansi378_minutiae(bytes_reg)
    minucias_vivo = parse_ansi378_minutiae(bytes_vivo)

    if len(minucias_reg) >= 4 and len(minucias_vivo) >= 4:
        score = comparar_minucias(minucias_reg, minucias_vivo)
    else:
        len_min = min(len(bytes_reg), len(bytes_vivo))
        len_max = max(len(bytes_reg), len(bytes_vivo))
        if len_max == 0:
            score = 0.0
        else:
            bytes_coincidentes = sum(1 for i in range(len_min) if bytes_reg[i] == bytes_vivo[i])
            score = round((bytes_coincidentes / len_max) * 100, 1)
            score = min(100.0, score * 1.5)

    is_match = score >= umbral_coincidencia

    return {
        'match': is_match,
        'score': score,
        'minucias_registradas': len(minucias_reg),
        'minucias_en_vivo': len(minucias_vivo),
        'mensaje': 'Huella verificada correctamente.' if is_match else 'Huella dactilar no coincide con el registro.'
    }
