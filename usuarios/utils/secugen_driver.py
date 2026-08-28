"""
SecuGen FDx SDK Pro Native Driver para Python
Integración 100% gratuita y perpetua para lectores SecuGen (Hamster Plus, Hamster IV, etc.)
Carga directa de sgfplib.dll en 64 bits.
"""

import os
import ctypes
from ctypes import byref, c_void_p, c_uint32, c_uint16, c_uint8, c_int, POINTER, Structure
import base64
import io
from PIL import Image

# Rutas donde buscar las DLLs de SecuGen
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SECUGEN_DIR = os.path.join(CURRENT_DIR, 'secugen')

# Intentar registrar directorio de DLLs en Windows Kernel32 y PATH
_dll_loaded = False
_sg_lib = None

try:
    if os.path.exists(SECUGEN_DIR):
        # 1. Configurar búsqueda en kernel32 para que sgfplib.dll encuentre sgfpamx.dll
        if hasattr(ctypes, 'windll') and hasattr(ctypes.windll, 'kernel32'):
            ctypes.windll.kernel32.SetDllDirectoryW(SECUGEN_DIR)

        # 2. Agregar a PATH
        if SECUGEN_DIR not in os.environ.get('PATH', ''):
            os.environ['PATH'] = SECUGEN_DIR + ';' + os.environ.get('PATH', '')

        # 3. add_dll_directory (Python 3.8+)
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(SECUGEN_DIR)

        # 4. Pre-cargar el motor de algoritmos de extracción (sgfpamx.dll)
        for dll_name in ['sgfpamx.dll', 'sgfdusdax64.dll', 'sgwsqlib.dll', 'sgbledev.dll']:
            p = os.path.join(SECUGEN_DIR, dll_name)
            if os.path.exists(p):
                try:
                    ctypes.WinDLL(p)
                except Exception:
                    pass

        # 5. Cargar librería principal
        dll_path = os.path.join(SECUGEN_DIR, 'sgfplib.dll')
        if os.path.exists(dll_path):
            _sg_lib = ctypes.WinDLL(dll_path)
            _dll_loaded = True
except Exception as e:
    print(f"[SECUGEN NATIVO] Error cargando sgfplib.dll: {e}")


# Constantes del SDK SecuGen
SG_DEV_AUTO = 0xFF
TEMPLATE_FORMAT_ANSI378 = 0x0100
TEMPLATE_FORMAT_SG400 = 0x0200
TEMPLATE_FORMAT_ISO19794 = 0x0300

# Mapeo de errores SecuGen
SECUGEN_ERRORS = {
    0: "Operación exitosa",
    1: "Error de creación de objeto",
    2: "Función no soportada",
    3: "Parámetro inválido",
    51: "Fallo de carga del sistema",
    52: "Fallo de inicialización del sensor",
    53: "Pérdida de datos de imagen",
    54: "Tiempo de espera agotado. No se colocó el dedo en el sensor a tiempo.",
    55: "Lector SecuGen Hamster Plus no detectado. Verifique el cable USB.",
    56: "Error de carga del driver del dispositivo",
    101: "Número insuficiente de minucias en la huella",
    105: "Fallo en la extracción de minucias. Apoye el dedo con mayor firmeza.",
    106: "Fallo de coincidencia",
}

# Estructuras C
class SGDeviceInfoParam(Structure):
    _fields_ = [
        ("DeviceID", c_uint32),
        ("DeviceSN", c_uint8 * 16),
        ("ComPort", c_uint32),
        ("ComSpeed", c_uint32),
        ("ImageWidth", c_uint32),
        ("ImageHeight", c_uint32),
        ("Contrast", c_uint32),
        ("Brightness", c_uint32),
        ("Gain", c_uint32),
        ("ImageDPI", c_uint32),
        ("FWVersion", c_uint32),
    ]

class SGFingerInfo(Structure):
    _fields_ = [
        ("FingerNumber", c_uint16),
        ("ViewNumber", c_uint16),
        ("ImpressionType", c_uint16),
        ("ImageQuality", c_uint16),
    ]


def verificar_sensor_conectado():
    """Verifica si el sensor físico SecuGen está conectado y listo."""
    if not _dll_loaded or not _sg_lib:
        return False, "La librería sgfplib.dll no está cargada."

    hFpm = c_void_p()
    ret = _sg_lib.SGFPM_Create(byref(hFpm))
    if ret != 0:
        return False, SECUGEN_ERRORS.get(ret, f"Error {ret}")

    try:
        ret_init = _sg_lib.SGFPM_Init(hFpm, SG_DEV_AUTO)
        if ret_init != 0:
            return False, SECUGEN_ERRORS.get(ret_init, f"Error inicializando: {ret_init}")

        ret_open = _sg_lib.SGFPM_OpenDevice(hFpm, 0)
        if ret_open != 0:
            return False, SECUGEN_ERRORS.get(ret_open, f"Lector no detectado (código {ret_open})")

        _sg_lib.SGFPM_CloseDevice(hFpm)
        return True, "Sensor SecuGen Hamster Plus conectado y operativo."
    finally:
        _sg_lib.SGFPM_Terminate(hFpm)


def capturar_huella_nativo(timeout_ms=10000, quality_min=40, formato="ANSI378"):
    """
    Captura una huella dactilar directamente desde el hardware SecuGen Hamster Plus.
    Retorna un diccionario con { 'success': bool, 'template': str (base64), 'imagen_base64': str, 'calidad': int, 'error': str }
    """
    if not _dll_loaded or not _sg_lib:
        return {
            'success': False,
            'error': 'Driver nativo sgfplib.dll no disponible.',
            'errorCode': -1
        }

    hFpm = c_void_p()
    ret = _sg_lib.SGFPM_Create(byref(hFpm))
    if ret != 0:
        return {
            'success': False,
            'error': f'Error creando instancia SecuGen: {SECUGEN_ERRORS.get(ret, ret)}',
            'errorCode': ret
        }

    try:
        # 1. Inicializar dispositivo automático
        ret = _sg_lib.SGFPM_Init(hFpm, SG_DEV_AUTO)
        if ret != 0:
            return {
                'success': False,
                'error': f'Error al inicializar sensor: {SECUGEN_ERRORS.get(ret, ret)}',
                'errorCode': ret
            }

        # 2. Abrir dispositivo USB (0 = auto)
        ret = _sg_lib.SGFPM_OpenDevice(hFpm, 0)
        if ret != 0:
            return {
                'success': False,
                'error': SECUGEN_ERRORS.get(ret, f'No se pudo abrir el lector SecuGen (Código: {ret})'),
                'errorCode': ret
            }

        # 3. Obtener dimensiones de imagen
        dev_info = SGDeviceInfoParam()
        ret = _sg_lib.SGFPM_GetDeviceInfo(hFpm, byref(dev_info))
        width = dev_info.ImageWidth or 260
        height = dev_info.ImageHeight or 300

        # 4. Establecer formato de template
        fmt_code = TEMPLATE_FORMAT_ANSI378 if formato == "ANSI378" else TEMPLATE_FORMAT_ISO19794
        _sg_lib.SGFPM_SetTemplateFormat(hFpm, fmt_code)

        # 5. Capturar imagen del sensor esperando que el usuario ponga el dedo
        img_buffer = (c_uint8 * (width * height))()
        ret = _sg_lib.SGFPM_GetImageEx(hFpm, img_buffer, timeout_ms, None, quality_min)

        if ret != 0:
            return {
                'success': False,
                'error': SECUGEN_ERRORS.get(ret, f'Error durante la captura: {ret}'),
                'errorCode': ret
            }

        # 6. Obtener calidad de la captura
        quality = c_uint32(0)
        _sg_lib.SGFPM_GetImageQuality(hFpm, width, height, img_buffer, byref(quality))

        # 7. Obtener tamaño máximo de template y extraer template
        max_size = c_uint32(0)
        _sg_lib.SGFPM_GetMaxTemplateSize(hFpm, byref(max_size))
        template_buffer = (c_uint8 * (max_size.value or 1024))()

        finger_info = SGFingerInfo()
        finger_info.FingerNumber = 0
        finger_info.ViewNumber = 0
        finger_info.ImpressionType = 0
        finger_info.ImageQuality = quality.value

        ret = _sg_lib.SGFPM_CreateTemplate(hFpm, byref(finger_info), img_buffer, template_buffer)
        if ret != 0:
            return {
                'success': False,
                'error': SECUGEN_ERRORS.get(ret, f'Error generando template dactilar: {ret}'),
                'errorCode': ret
            }

        # Obtener tamaño real del template
        template_size = c_uint32(0)
        _sg_lib.SGFPM_GetTemplateSize(hFpm, template_buffer, byref(template_size))
        real_size = template_size.value if template_size.value > 0 else max_size.value

        template_bytes = bytes(template_buffer[:real_size])
        template_b64 = base64.b64encode(template_bytes).decode('ascii')

        # 8. Convertir imagen RAW a JPEG en memoria para visualización web
        raw_bytes = bytes(img_buffer)
        jpeg_b64 = ""
        try:
            img = Image.frombytes('L', (width, height), raw_bytes)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            jpeg_b64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode('ascii')
        except Exception as e:
            print(f"[SECUGEN] Error creando JPEG de vista previa: {e}")

        _sg_lib.SGFPM_CloseDevice(hFpm)

        return {
            'success': True,
            'template': template_b64,
            'imagen_base64': jpeg_b64,
            'calidad': int(quality.value),
            'formato': formato,
            'width': int(width),
            'height': int(height),
            'mensaje': f'Huella capturada exitosamente con SecuGen Hamster Plus (Calidad: {quality.value}%)'
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Excepción durante la captura: {str(e)}',
            'errorCode': -99
        }
    finally:
        _sg_lib.SGFPM_Terminate(hFpm)


def comparar_templates_nativo(template1_b64, template2_b64, security_level=5):
    """
    Compara 2 templates ANSI-378 usando el motor de matching nativo C++ de SecuGen.
    Retorna { 'match': bool, 'score': int, 'error': str }
    """
    if not _dll_loaded or not _sg_lib:
        from .biometria_dactilar import comparar_templates_huella
        return comparar_templates_huella(template1_b64, template2_b64)

    if not template1_b64 or not template2_b64:
        return {'match': False, 'score': 0, 'mensaje': 'Uno de los templates está vacío.'}

    if template1_b64.strip() == template2_b64.strip():
        return {'match': True, 'score': 100, 'mensaje': 'Coincidencia exacta de huella (100%).'}

    try:
        t1_bytes = base64.b64decode(template1_b64)
        t2_bytes = base64.b64decode(template2_b64)
    except Exception as e:
        return {'match': False, 'score': 0, 'mensaje': f'Error decodificando Base64: {e}'}

    hFpm = c_void_p()
    ret = _sg_lib.SGFPM_Create(byref(hFpm))
    if ret != 0:
        from .biometria_dactilar import comparar_templates_huella
        return comparar_templates_huella(template1_b64, template2_b64)

    try:
        _sg_lib.SGFPM_Init(hFpm, SG_DEV_AUTO)
        _sg_lib.SGFPM_SetTemplateFormat(hFpm, TEMPLATE_FORMAT_ANSI378)

        t1_buf = (c_uint8 * len(t1_bytes)).from_buffer_copy(t1_bytes)
        t2_buf = (c_uint8 * len(t2_bytes)).from_buffer_copy(t2_bytes)

        matched = c_int(0)
        score = c_uint32(0)

        # MatchTemplate y GetMatchingScore
        _sg_lib.SGFPM_MatchTemplate(hFpm, t1_buf, t2_buf, security_level, byref(matched))
        _sg_lib.SGFPM_GetMatchingScore(hFpm, t1_buf, t2_buf, byref(score))

        score_val = int(score.value)
        # Normalizar score de SecuGen (típicamente 0 a 199+) a porcentaje (0 a 100%)
        porcentaje = min(100, int((score_val / 150.0) * 100)) if score_val > 0 else 0
        if matched.value:
            porcentaje = max(porcentaje, 80)

        is_match = bool(matched.value) or porcentaje >= 70

        if not is_match:
            # Fallback al matcher de minucias algorítmico
            from .biometria_dactilar import comparar_templates_huella
            resultado_alg = comparar_templates_huella(template1_b64, template2_b64)
            if resultado_alg['match']:
                return resultado_alg

        return {
            'match': is_match,
            'score': porcentaje,
            'raw_score': score_val,
            'mensaje': f'Huella verificada correctamente ({porcentaje}% coincidencia)' if is_match else f'Huella no coincide ({porcentaje}% coincidencia)'
        }
    finally:
        _sg_lib.SGFPM_Terminate(hFpm)

