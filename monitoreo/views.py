import os
import cv2
import base64
import numpy as np
import uuid
import threading
import time
from django.conf import settings
from django.db.models import Q
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from usuarios.models import Acceso, Persona, ConfiguracionCamara
from django.contrib.auth.decorators import login_required
from usuarios.utils.security import encrypt_bytes
from usuarios.utils.deep_learning import DeepFaceEngine
from usuarios.utils.camera_discovery import scan_all_cameras, test_camera_connection
from facial_secure.ip_camera import YooseeIPCamera
from django.utils import timezone
from .models import ProtocoloLockdown
from modelo.detector_accesorios import detectar_accesorios_prohibidos
from modelo.anti_spoofing import verificar_prueba_de_vida

# ==========================================
# MOTOR DE INFERENCIA DEEP LEARNING EN MEMORIA
# ==========================================
_cached_matrix = None
_cached_personas = []
_last_cache_update = 0
_cache_lock = threading.Lock()

def get_cached_embeddings():
    """Recarga los vectores de Deep Learning de la base de datos de forma dinámica."""
    global _cached_matrix, _cached_personas, _last_cache_update
    ahora = time.time()
    with _cache_lock:
        if _cached_matrix is None or (ahora - _last_cache_update) > 2.0:
            personas = list(
                Persona.objects.filter(biometria_facial=True)
                .exclude(embedding_facial__isnull=True)
                .only('id', 'nombre', 'apellido', 'estado', 'tipo_persona', 'rut', 'embedding_facial')
            )
            if len(personas) > 0:
                matrix = np.array([p.embedding_facial for p in personas], dtype=np.float32)
                norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-7
                _cached_matrix = matrix / norms
                _cached_personas = personas
            else:
                _cached_matrix = None
                _cached_personas = []
            _last_cache_update = ahora
    return _cached_matrix, _cached_personas

# ==========================================
# GESTIÓN MULTI-CÁMARA CONCURRENTE EN MEMORIA
# ==========================================
_camera_instances = {}
_camera_lock = threading.Lock()

def get_shared_ip_camera(cam_id=None, force_restart=False):
    """Obtiene o reinicia la instancia de captura de video para la cámara solicitada."""
    global _camera_instances
    with _camera_lock:
        if cam_id:
            cfg = ConfiguracionCamara.get_activa(cam_id=cam_id)
        else:
            cfg = ConfiguracionCamara.get_activa()

        if not cfg:
            return None

        key = cfg.id

        if force_restart and key in _camera_instances:
            try:
                _camera_instances[key].release()
            except Exception:
                pass
            del _camera_instances[key]

        if key not in _camera_instances or not _camera_instances[key].running:
            _camera_instances[key] = YooseeIPCamera(
                tipo=cfg.tipo,
                ip=cfg.ip,
                user=cfg.usuario,
                password=cfg.password,
                stream=cfg.stream,
                webcam_index=cfg.webcam_index
            )
        return _camera_instances[key]


def release_camera_instance(cam_id):
    """Libera los recursos de un worker de cámara eliminado."""
    global _camera_instances
    with _camera_lock:
        if cam_id in _camera_instances:
            try:
                _camera_instances[cam_id].release()
            except Exception:
                pass
            del _camera_instances[cam_id]


def generar_frame_standby(nombre_cam, cfg=None):
    """Genera un fotograma dinámico y profesional estilo HUD táctico mientras se conecta o si no hay señal."""
    h, w = 360, 640
    frame = np.full((h, w, 3), (24, 18, 12), dtype=np.uint8)

    # Líneas guía HUD sutiles
    cv2.line(frame, (20, 40), (w - 20, 40), (55, 42, 28), 1)
    cv2.line(frame, (20, h - 35), (w - 20, h - 35), (55, 42, 28), 1)

    ahora_str = time.strftime('%Y-%m-%d  %H:%M:%S')
    cv2.putText(frame, "FACIAL SECURE // VISTA DE SEGURIDAD", (25, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 200, 255), 1)
    cv2.putText(frame, ahora_str, (w - 185, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, (160, 160, 160), 1)

    cv2.putText(frame, f"CAMARA: {str(nombre_cam).upper()}", (35, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 0.70, (255, 255, 255), 2)

    # Indicador de estado y pulsos
    t_mod = (int(time.time() * 3) % 4)
    puntos = "." * (t_mod + 1)

    if cfg and cfg.tipo == 'ip_yoosee':
        url_info = f"rtsp://{cfg.ip}:{cfg.puerto_rtsp}/{cfg.stream}"
        cv2.putText(frame, f"ORIGEN: {url_info}", (35, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (200, 200, 200), 1)
        cv2.putText(frame, f"Sincronizando flujo de red{puntos}", (35, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 215, 255), 2)
        cv2.putText(frame, "Negociando fotogramas clave H.264/H.265...", (35, 210),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 160, 180), 1)

        is_cloud = bool(os.environ.get('RENDER') or 'render.com' in os.environ.get('DATABASE_URL', ''))
        if is_cloud and cfg.ip and (cfg.ip.startswith('192.168.') or cfg.ip.startswith('10.') or cfg.ip.startswith('172.')):
            cv2.putText(frame, "AVISO CLOUD: Servidor Render en la nube no puede rutear IPs privadas LAN.", (35, 265),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 140, 255), 1)
            cv2.putText(frame, "Para Render usa la camara del navegador (Iriun) o corre local: python manage.py runserver", (35, 290),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
    else:
        cv2.putText(frame, f"Conectando sensor de video local{puntos}", (35, 155),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 215, 255), 2)
        cv2.putText(frame, "Esperando captura DirectShow / USB...", (35, 190),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (140, 160, 180), 1)

    cv2.putText(frame, "[ESTADO: CONECTANDO STREAM]", (25, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 200, 255), 1)
    cv2.putText(frame, "MODO: TIEMPO REAL", (w - 165, h - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (100, 220, 100), 1)

    return frame


def generar_stream_con_reconocimiento(cam_id=None, flujo=None):
    """Generador continuo no-bloqueante con Inferencia Deep Learning SFace + YuNet."""
    engine = DeepFaceEngine.get_instance()
    ultimo_registro_tiempo = {}
    frame_count = 0

    # Carga inicial de embeddings
    get_cached_embeddings()

    cfg = ConfiguracionCamara.get_activa(cam_id=cam_id)
    nombre_cam = cfg.nombre if cfg else "Cámara Principal"
    if flujo:
        tag = 'Ingreso' if flujo.lower() == 'ingreso' else 'Egreso'
        nombre_cam_registrado = f"{nombre_cam} ({tag})"
    else:
        nombre_cam_registrado = nombre_cam
    cam_pk = cfg.id if cfg else 0

    while True:
        cam = get_shared_ip_camera(cam_id=cam_pk)
        ret, frame = (False, None)
        if cam is not None:
            ret, frame = cam.get_latest_frame()

        if not ret or frame is None:
            # Enviar frame de espera dinámico y táctico para informar al usuario en tiempo real
            frame = generar_frame_standby(nombre_cam, cfg)
            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield (b'--frame\\r\\n'
                   b'Content-Type: image/jpeg\\r\\n\\r\\n' + jpeg.tobytes() + b'\\r\\n')
            time.sleep(0.08)
            continue

        frame_count += 1
        h, w = frame.shape[:2]

        # Procesar IA cada 2 frames para optimizar CPU
        if frame_count % 2 == 0:
            faces = engine.detect_faces(frame)
            matrix, personas_list = get_cached_embeddings()
            ahora = time.time()

            for face in faces:
                fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                x1 = max(0, fx)
                y1 = max(0, fy)
                x2 = min(w, fx + fw)
                y2 = min(h, fy + fh)

                color_box = (0, 200, 255) # Ámbar
                label_text = "Sujeto Desconocido"
                coincidencia = 0.0
                persona = None
                estado = "REVISION"

                # 5 puntos faciales (ojos, nariz, boca)
                landmarks = []
                try:
                    if len(face) >= 14:
                        landmarks = [
                            (int(face[4]), int(face[5])),
                            (int(face[6]), int(face[7])),
                            (int(face[8]), int(face[9])),
                            (int(face[10]), int(face[11])),
                            (int(face[12]), int(face[13]))
                        ]
                except Exception:
                    landmarks = []

                # EVALUACIÓN DE ACCESORIOS PROHIBIDOS Y PRUEBA DE VIDA PASIVA (ANTI-SPOOFING)
                analisis_accesorios = detectar_accesorios_prohibidos(frame, (fx, fy, fw, fh), landmarks)
                analisis_liveness = verificar_prueba_de_vida(frame, (fx, fy, fw, fh))

                try:
                    aligned_face, live_feat = engine.align_and_extract_feature(frame, face)
                    
                    if matrix is not None and len(personas_list) > 0 and live_feat is not None:
                        best_persona, score, coincidencia = engine.match_against_matrix(live_feat, matrix, personas_list)

                        is_egreso_cam = bool(flujo and str(flujo).lower() == 'egreso') or ('egreso' in nombre_cam.lower()) or ('salida' in nombre_cam.lower())
                        es_interno = (getattr(best_persona, 'tipo_persona', '') == 'interno')

                        # REGLA 1: DETECCIÓN DE SPOOFING (FOTO / PANTALLA)
                        if not analisis_liveness['es_real']:
                            persona = best_persona
                            estado = 'DENEGADO'
                            color_box = (0, 0, 255) # Rojo táctico
                            label_text = f"[ANTI-SPOOFING] FOTO/PANTALLA BLOQUEADA (Sim: {coincidencia:.0f}%)"

                        # REGLA 2: EGRESO PARA INTERNOS -> PROTOCOLO LOCKDOWN
                        elif is_egreso_cam and es_interno and coincidencia >= 45.0:
                            persona = best_persona
                            estado = 'DENEGADO'
                            color_box = (0, 0, 255) # Rojo táctico de emergencia
                            label_text = f"ALERTA INTERNO: {persona.nombre} {persona.apellido} ({coincidencia:.0f}%) [DENEGADO]"
                            ProtocoloLockdown.activar(
                                motivo=f"ALERTA FUGA: Detección de Interno ({persona.nombre} {persona.apellido}) en Cámara de Egreso {nombre_cam_registrado}",
                                origen='AUTOMATICO_FUGA'
                            )

                        # REGLA 3: CONTROL DE TRÁNSITO SECUENCIAL (ANTI-PASSBACK)
                        elif not is_egreso_cam and coincidencia >= 65.0 and getattr(best_persona, 'esta_dentro_del_recinto', lambda: False)():
                            # Ya ingresó al penal: no volver a detectar en el ingreso hasta que se haga el egreso
                            continue

                        elif is_egreso_cam and coincidencia >= 65.0 and not es_interno and not getattr(best_persona, 'esta_dentro_del_recinto', lambda: False)():
                            # Ya egresó del penal: no volver a detectar en el egreso hasta que se haga el ingreso
                            continue

                        elif coincidencia >= 65.0:
                            persona = best_persona
                            permitido = (persona.estado == 'activo')
                            if not analisis_accesorios['rostro_despejado']:
                                estado = 'REVISION'
                                color_box = (0, 165, 255) # Ámbar
                                label_text = f"{persona.nombre} {persona.apellido} [RETIRAR {', '.join(analisis_accesorios['accesorios']).upper()}]"
                            elif permitido:
                                estado = 'PERMITIDO'
                                color_box = (0, 255, 0) # Verde
                                label_text = f"{persona.nombre} {persona.apellido} ({coincidencia:.0f}%)"
                            else:
                                estado = 'DENEGADO'
                                color_box = (0, 0, 255) # Rojo
                                label_text = f"{persona.nombre} {persona.apellido} ({coincidencia:.0f}%)"

                        elif coincidencia >= 45.0:
                            persona = best_persona
                            estado = 'REVISION'
                            color_box = (0, 165, 255) # Ámbar
                            if not analisis_accesorios['rostro_despejado']:
                                label_text = f"{persona.nombre} {persona.apellido} [RETIRAR {', '.join(analisis_accesorios['accesorios']).upper()}]"
                            else:
                                label_text = f"{persona.nombre} {persona.apellido} ({coincidencia:.0f}%)"
                        else:
                            estado = 'DENEGADO'
                            color_box = (0, 0, 255)
                            label_text = f"Sujeto Desconocido ({coincidencia:.0f}%)"
                            persona = None
                    else:
                        coincidencia = 0.0
                        estado = 'DENEGADO'
                        color_box = (0, 0, 255)
                        label_text = "Sujeto Desconocido"

                except Exception as e:
                    print("Error en inferencia Deep Learning:", e)

                # Dibujar recuadro táctico
                cv2.rectangle(frame, (x1, y1), (x2, y2), color_box, 2)
                if not analisis_liveness['es_real']:
                    cv2.rectangle(frame, (max(0, x1 - 4), max(0, y1 - 4)), (min(w, x2 + 4), min(h, y2 + 4)), (0, 0, 255), 2)
                    cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 180), -1)
                    cv2.putText(frame, "ALERTA ANTI-SPOOFING: SUPLANTACION CON FOTO O PANTALLA DETECTADA", (14, 24),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2)
                elif is_egreso_cam and bool(persona and getattr(persona, 'tipo_persona', '') == 'interno') and coincidencia >= 45.0:
                    cv2.rectangle(frame, (0, 0), (w, 38), (0, 0, 200), -1)
                    cv2.putText(frame, "ALERTA MAXIMA: INTENTO DE EGRESO NO AUTORIZADO DE INTERNO", (15, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)
                
                # Dibujar 5 puntos faciales (ojos, nariz, boca)
                try:
                    landmarks = [
                        (int(face[4]), int(face[5])),
                        (int(face[6]), int(face[7])),
                        (int(face[8]), int(face[9])),
                        (int(face[10]), int(face[11])),
                        (int(face[12]), int(face[13]))
                    ]
                    for (lx, ly) in landmarks:
                        if 0 <= lx < w and 0 <= ly < h:
                            cv2.circle(frame, (lx, ly), 2, color_box, -1)
                except Exception:
                    pass

                cv2.putText(frame, label_text, (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color_box, 2)

                # Etiqueta inferior de Anti-Spoofing en el recuadro
                spoof_tag = (
                    f"ANTI-SPOOFING: HUMANO VIVO ({analisis_liveness['score']:.0f}%)"
                    if analisis_liveness['es_real']
                    else f"ANTI-SPOOFING: FALSO/2D ({analisis_liveness['score']:.0f}% VIDA) - BLOQUEADO"
                )
                spoof_color = (0, 230, 118) if analisis_liveness['es_real'] else (0, 0, 255)
                cv2.putText(frame, spoof_tag, (x1, min(h - 10, y2 + 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, spoof_color, 2)

                # Registrar acceso en la BD únicamente cuando la cámara tiene un flujo operativo asignado ('ingreso' o 'egreso')
                if flujo and (str(flujo).lower() in ['ingreso', 'egreso']):
                    registro_key = f"{persona.id if persona else 'desconocido'}_{cam_pk}_{str(flujo).lower()}"
                    if registro_key not in ultimo_registro_tiempo or (ahora - ultimo_registro_tiempo[registro_key]) > 5.0:
                        ultimo_registro_tiempo[registro_key] = ahora
                    try:
                        rostro_color = frame[y1:y2, x1:x2]
                        if rostro_color.size > 0:
                            # Recorte de persona (cabeza + torso/vestimenta)
                            fh = y2 - y1
                            fw = x2 - x1
                            hf, wf = frame.shape[:2]
                            cy1 = max(0, int(y1 - 0.25 * fh))
                            cy2 = min(hf, int(y2 + 3.2 * fh))
                            cx1 = max(0, int(x1 - 0.7 * fw))
                            cx2 = min(wf, int(x2 + 0.7 * fw))
                            cuerpo_crop = frame[cy1:cy2, cx1:cx2]
                            if cuerpo_crop.size == 0:
                                cuerpo_crop = rostro_color

                            # Auditoría de vestimenta IA
                            from accesos.ai_vestimenta import analizar_vestimenta_individual
                            try:
                                analisis_ropa = analizar_vestimenta_individual(cuerpo_crop)
                            except Exception:
                                analisis_ropa = None

                            desc_ropa = ""
                            if analisis_ropa and analisis_ropa.get('exito'):
                                desc_ropa = f"👕 {analisis_ropa['color_superior']} | 👖 {analisis_ropa['color_inferior']}"

                            _, buf = cv2.imencode('.jpg', cuerpo_crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
                            enc_bytes = encrypt_bytes(buf.tobytes())

                            es_spoof = not analisis_liveness['es_real']
                            es_alerta_fuga = is_egreso_cam and bool(persona and getattr(persona, 'tipo_persona', '') == 'interno')
                            if es_spoof:
                                nombre_detectado_bd = f"🚨 SPOOFING [{analisis_liveness['score']}%]: {persona.nombre if persona else 'Desconocido'}"
                            elif es_alerta_fuga:
                                nombre_detectado_bd = f"¡ALERTA FUGA! {persona.nombre} {persona.apellido} (Interno)"
                            elif not analisis_accesorios['rostro_despejado']:
                                nombre_detectado_bd = f"{persona.nombre if persona else 'Desconocido'} [Accesorios: {', '.join(analisis_accesorios['accesorios'])}]"
                            else:
                                nombre_detectado_bd = persona.nombre if persona else "Sujeto Desconocido"

                            estado_bd = 'REVISION' if (es_spoof and persona and coincidencia >= 45.0 and not es_alerta_fuga) else estado
                            acceso = Acceso.objects.create(
                                persona=persona,
                                nombre_detectado=nombre_detectado_bd,
                                coincidencia=coincidencia,
                                resultado=estado_bd,
                                camara=nombre_cam_registrado,
                                descripcion_vestimenta=desc_ropa,
                                resuelto=False if es_alerta_fuga else (True if estado_bd == 'PERMITIDO' else False)
                            )
                            acceso.foto_validacion.save(
                                f"{uuid.uuid4()}.jpg",
                                ContentFile(enc_bytes),
                                save=True
                            )
                            if estado == 'PERMITIDO':
                                from accesos.models import sincronizar_visita_externa_desde_acceso
                                sincronizar_visita_externa_desde_acceso(
                                    acceso,
                                    frame=cuerpo_crop,
                                    analisis_ropa=analisis_ropa
                                )
                    except Exception as e:
                        print("Error registrando acceso:", e)

        # Codificar en JPEG a 25-30 FPS
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.03)


@login_required
def video_feed(request):
    """Endpoint de transmisión en vivo MJPEG para Monitoreo y Dashboard."""
    cam_id = request.GET.get('cam_id')
    flujo = request.GET.get('flujo')
    return StreamingHttpResponse(
        generar_stream_con_reconocimiento(cam_id=cam_id, flujo=flujo),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


@login_required
def monitoreo(request):
    flujo = request.GET.get('flujo', 'ingreso')
    qs = Acceso.objects.select_related('persona')
    if flujo == 'egreso':
        qs = qs.filter(Q(camara__icontains='Egreso') | Q(camara__icontains='Salida'))
    else:
        qs = qs.filter(Q(camara__icontains='Ingreso') | (~Q(camara__icontains='Egreso') & ~Q(camara__icontains='Salida')))
    accesos = qs.order_by('-fecha_hora')[:20]
    camaras = ConfiguracionCamara.objects.filter(activa=True).order_by('id')
    cam_activa = camaras.first() if camaras.exists() else ConfiguracionCamara.get_activa()
    return render(
        request,
        'monitoreo/monitoreo.html',
        {
            'accesos': accesos,
            'camaras': camaras,
            'camara_activa': cam_activa,
            'flujo_inicial': flujo
        }
    )


_browser_cooldowns = {}
_browser_cooldown_lock = threading.Lock()

@csrf_exempt
@login_required
def detectar_rostros(request):
    """Endpoint para detección e inferencia Deep Learning sobre fotogramas base64."""
    if request.method == 'POST':
        foto_base64 = request.POST.get('foto_base64')
        camara_base = request.POST.get('camara_nombre', 'Cámara del Navegador').strip() or 'Cámara del Navegador'
        flujo = request.POST.get('flujo', 'ingreso').strip().lower()
        tag = 'Ingreso' if flujo == 'ingreso' else 'Egreso'
        camara_clean = camara_base.replace('(Ingreso)', '').replace('(Egreso)', '').strip()
        camara_nombre = f"{camara_clean} ({tag})"
        if not foto_base64:
            return JsonResponse({'rostros': []})

        try:
            formato, imgstr = foto_base64.split(';base64,')
            img_bytes = base64.b64decode(imgstr)
            npimg = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

            engine = DeepFaceEngine.get_instance()
            faces = engine.detect_faces(frame)
            matrix, personas_list = get_cached_embeddings()
            ahora = time.time()

            resultados = []
            aviso_transito = None

            for face in faces:
                fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                x1 = max(0, fx)
                y1 = max(0, fy)
                x2 = min(frame.shape[1], fx + fw)
                y2 = min(frame.shape[0], fy + fh)

                nombre = 'Sujeto Desconocido'
                coincidencia = 0.0
                estado = 'REVISION'
                persona = None
                es_alerta_interno = False

                # 5 puntos faciales para HUD táctico
                landmarks = []
                if len(face) >= 14:
                    landmarks = [
                        [int(face[4]), int(face[5])],
                        [int(face[6]), int(face[7])],
                        [int(face[8]), int(face[9])],
                        [int(face[10]), int(face[11])],
                        [int(face[12]), int(face[13])]
                    ]

                analisis_accesorios = detectar_accesorios_prohibidos(frame, (fx, fy, fw, fh), landmarks)
                analisis_liveness = verificar_prueba_de_vida(frame, (fx, fy, fw, fh))

                try:
                    aligned_face, live_feat = engine.align_and_extract_feature(frame, face)
                    if matrix is not None and len(personas_list) > 0 and live_feat is not None:
                        best_persona, score, coincidencia = engine.match_against_matrix(live_feat, matrix, personas_list)

                        is_egreso_cam = (flujo == 'egreso') or ('egreso' in camara_nombre.lower()) or ('salida' in camara_nombre.lower())
                        es_interno = (getattr(best_persona, 'tipo_persona', '') == 'interno')

                        # REGLA 1: DETECCIÓN DE SPOOFING (FOTO / PANTALLA)
                        if not analisis_liveness['es_real']:
                            persona = best_persona if coincidencia >= 45.0 else None
                            permitido = False
                            estado = 'DENEGADO'
                            sujeto_ref = f"{best_persona.nombre} {best_persona.apellido}" if (best_persona and coincidencia >= 45.0) else "Sujeto"
                            nombre = f"🚨 SPOOFING [FOTO/PANTALLA]: {sujeto_ref}"

                        # REGLA 2: EGRESO PARA INTERNOS -> PROTOCOLO LOCKDOWN
                        elif is_egreso_cam and es_interno and coincidencia >= 45.0:
                            persona = best_persona
                            permitido = False
                            estado = 'DENEGADO'
                            nombre = f"ALERTA INTERNO: {persona.nombre} {persona.apellido}"
                            es_alerta_interno = True
                            ProtocoloLockdown.activar(
                                motivo=f"ALERTA FUGA: Detección de Interno ({persona.nombre} {persona.apellido}) en Cámara de Egreso {camara_nombre}",
                                origen='AUTOMATICO_FUGA'
                            )

                        # REGLA 3: CONTROL DE TRÁNSITO SECUENCIAL (ANTI-PASSBACK)
                        elif not is_egreso_cam and coincidencia >= 65.0 and getattr(best_persona, 'esta_dentro_del_recinto', lambda: False)():
                            # Ya ingresó al penal: no volver a detectar en el ingreso hasta que se haga el egreso
                            aviso_transito = f"ℹ️ {best_persona.nombre} {best_persona.apellido} ya ingresó al recinto (En permanencia). Cambie a pestaña EGRESOS para registrar su salida."
                            continue

                        elif is_egreso_cam and coincidencia >= 65.0 and not es_interno and not getattr(best_persona, 'esta_dentro_del_recinto', lambda: False)():
                            # Ya egresó del penal: no volver a detectar en el egreso hasta que se haga el ingreso
                            aviso_transito = f"ℹ️ {best_persona.nombre} {best_persona.apellido} ya completó su egreso (Fuera del penal). Cambie a pestaña INGRESOS para registrar entrada."
                            continue

                        elif coincidencia >= 65.0:
                            persona = best_persona
                            permitido = (persona.estado == 'activo')
                            if not analisis_accesorios['rostro_despejado']:
                                estado = 'REVISION'
                                nombre = f"{persona.nombre} {persona.apellido} [RETIRAR {', '.join(analisis_accesorios['accesorios']).upper()}]"
                            else:
                                estado = 'PERMITIDO' if permitido else 'DENEGADO'
                                nombre = f"{persona.nombre} {persona.apellido}"
                        elif coincidencia >= 45.0:
                            persona = best_persona
                            estado = 'REVISION'
                            if not analisis_accesorios['rostro_despejado']:
                                nombre = f"{persona.nombre} {persona.apellido} [RETIRAR {', '.join(analisis_accesorios['accesorios']).upper()}]"
                            else:
                                nombre = f"{persona.nombre} {persona.apellido}"
                        else:
                            estado = 'DENEGADO'
                            nombre = "Sujeto Desconocido"
                            persona = None
                    elif not analisis_liveness['es_real']:
                        estado = 'DENEGADO'
                        nombre = "🚨 SPOOFING [FOTO/PANTALLA DETECTADA]"
                except Exception as e:
                    print("Error en inferencia webcam:", e)

                # Cooldown de 4 segundos por sujeto y estado para no bloquear transiciones a REVISION
                user_id = request.user.id if request.user.is_authenticated else 'anon'
                registro_key = f"{persona.id if persona else 'desconocido'}_{estado}_{user_id}"
                nuevo_registro = False
                with _browser_cooldown_lock:
                    if registro_key not in _browser_cooldowns or (ahora - _browser_cooldowns[registro_key]) > 4.0:
                        _browser_cooldowns[registro_key] = ahora
                        nuevo_registro = True

                avatar_url = f"/media/secure/{persona.foto.name}" if (persona and persona.foto) else "/static/img/no-face.jpg"

                rostro_color = frame[y1:y2, x1:x2]
                if nuevo_registro and rostro_color.size > 0:
                    try:
                        # Recorte de persona (cabeza + torso/vestimenta)
                        fh = y2 - y1
                        fw = x2 - x1
                        hf, wf = frame.shape[:2]
                        cy1 = max(0, int(y1 - 0.25 * fh))
                        cy2 = min(hf, int(y2 + 3.2 * fh))
                        cx1 = max(0, int(x1 - 0.7 * fw))
                        cx2 = min(wf, int(x2 + 0.7 * fw))
                        cuerpo_crop = frame[cy1:cy2, cx1:cx2]
                        if cuerpo_crop.size == 0:
                            cuerpo_crop = rostro_color

                        # Auditoría de vestimenta IA
                        from accesos.ai_vestimenta import analizar_vestimenta_individual
                        try:
                            analisis_ropa = analizar_vestimenta_individual(cuerpo_crop)
                        except Exception:
                            analisis_ropa = None

                        desc_ropa = ""
                        if analisis_ropa and analisis_ropa.get('exito'):
                            desc_ropa = f"👕 {analisis_ropa['color_superior']} | 👖 {analisis_ropa['color_inferior']}"

                        _, buffer = cv2.imencode('.jpg', cuerpo_crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
                        enc_bytes = encrypt_bytes(buffer.tobytes())

                        is_alerta_fuga = es_alerta_interno
                        nombre_guardar = f"¡ALERTA FUGA! {persona.nombre} {persona.apellido} (Interno)" if is_alerta_fuga else nombre
                        es_spoof_conocido = (not analisis_liveness['es_real']) and (persona is not None) and (coincidencia >= 45.0) and (not is_alerta_fuga)
                        estado_guardar = 'REVISION' if es_spoof_conocido else estado

                        acceso = Acceso.objects.create(
                            persona=persona,
                            nombre_detectado=nombre_guardar,
                            coincidencia=coincidencia,
                            resultado=estado_guardar,
                            camara=camara_nombre,
                            descripcion_vestimenta=desc_ropa,
                            resuelto=False if is_alerta_fuga else (True if estado_guardar == 'PERMITIDO' else False)
                        )
                        foto_name = f"{uuid.uuid4()}.jpg"
                        acceso.foto_validacion.save(
                            foto_name,
                            ContentFile(enc_bytes),
                            save=True
                        )
                        if estado == 'PERMITIDO':
                            from accesos.models import sincronizar_visita_externa_desde_acceso
                            sincronizar_visita_externa_desde_acceso(
                                acceso,
                                usuario=request.user,
                                frame=cuerpo_crop,
                                analisis_ropa=analisis_ropa
                            )
                        avatar_url = f"/media/secure/{acceso.foto_validacion.name}"
                    except Exception as e:
                        print("Error guardando acceso desde navegador:", e)

                # 5 puntos faciales para HUD táctico
                landmarks = []
                if len(face) >= 14:
                    landmarks = [
                        [int(face[4]), int(face[5])],
                        [int(face[6]), int(face[7])],
                        [int(face[8]), int(face[9])],
                        [int(face[10]), int(face[11])],
                        [int(face[12]), int(face[13])]
                    ]

                resultados.append({
                    'id': f'{fx}-{fy}-{fw}-{fh}',
                    'x': int(fx),
                    'y': int(fy),
                    'w': int(fw),
                    'h': int(fh),
                    'landmarks': landmarks,
                    'estado': estado,
                    'coincidencia': float(round(coincidencia, 1)),
                    'nombre': nombre,
                    'tipo': persona.get_tipo_persona_display() if persona else 'Desconocido',
                    'rut': persona.rut if persona else '---',
                    'hora': time.strftime('%H:%M:%S'),
                    'avatar_url': avatar_url,
                    'nuevo_registro': nuevo_registro,
                    'es_alerta_interno': es_alerta_interno,
                    'accesorios': {
                        'rostro_despejado': analisis_accesorios['rostro_despejado'],
                        'items': analisis_accesorios['accesorios'],
                        'mensaje': analisis_accesorios['mensaje_alerta']
                    },
                    'prueba_vida': {
                        'es_real': analisis_liveness['es_real'],
                        'score': analisis_liveness['score'],
                        'dictamen': analisis_liveness['dictamen'],
                        'alertas': analisis_liveness['alertas_spoof']
                    },
                    'lockdown_activado': ProtocoloLockdown.esta_activo()
                })

            return JsonResponse({'rostros': resultados, 'aviso_transito': aviso_transito})
        except Exception as e:
            return JsonResponse({'rostros': [], 'error': str(e), 'aviso_transito': None})

    return JsonResponse({'rostros': [], 'aviso_transito': None})


@login_required
def ultimas_detecciones_ajax(request):
    """Retorna las últimas 15 detecciones en formato JSON filtradas por flujo sin mezclar."""
    flujo = request.GET.get('flujo')
    qs = Acceso.objects.select_related('persona')
    if flujo == 'ingreso':
        qs = qs.filter(Q(camara__icontains='Ingreso') | (~Q(camara__icontains='Egreso') & ~Q(camara__icontains='Salida')))
    elif flujo == 'egreso':
        qs = qs.filter(Q(camara__icontains='Egreso') | Q(camara__icontains='Salida'))

    accesos = qs.order_by('-fecha_hora')[:15]
    items = []
    for acc in accesos:
        if acc.foto_validacion:
            foto_url = f"/media/secure/{acc.foto_validacion.name}"
        elif acc.persona and acc.persona.foto:
            foto_url = f"/media/secure/{acc.persona.foto.name}"
        else:
            foto_url = "/static/img/no-face.jpg"

        es_egreso = ('egreso' in acc.camara.lower()) or ('salida' in acc.camara.lower())
        es_alerta_interno = bool(acc.persona and getattr(acc.persona, 'tipo_persona', '') == 'interno' and es_egreso)
        items.append({
            'id': acc.id,
            'nombre': f"{acc.persona.nombre} {acc.persona.apellido}" if acc.persona else (acc.nombre_detectado or "Sujeto Desconocido"),
            'tipo': acc.persona.get_tipo_persona_display() if acc.persona else "Externo",
            'hora': acc.fecha_hora.strftime('%H:%M:%S') if acc.fecha_hora else "",
            'camara': acc.camara or "Cámara",
            'flujo': 'egreso' if es_egreso else 'ingreso',
            'resultado': acc.resultado,
            'coincidencia': round(acc.coincidencia, 0) if acc.coincidencia else 0,
            'foto_url': foto_url,
            'es_alerta_interno': es_alerta_interno
        })
    return JsonResponse({'success': True, 'flujo': flujo, 'detecciones': items})


@csrf_exempt
@login_required
def probar_conexion_camara_ajax(request):
    """Prueba en tiempo real la conexión y credenciales de una cámara IP por RTSP antes o después de asignarla."""
    if request.method == 'POST':
        try:
            import json
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST

            cam_id = data.get('cam_id')
            if cam_id:
                cfg = ConfiguracionCamara.objects.filter(id=cam_id).first()
                if cfg:
                    if cfg.tipo == 'webcam':
                        return JsonResponse({'success': True, 'status': 200, 'message': f'Webcam USB #{cfg.webcam_index} configurada en el servidor.'})
                    ip = cfg.ip
                    puerto_rtsp = cfg.puerto_rtsp
                    usuario = cfg.usuario
                    password = cfg.password
                    stream = cfg.stream
                else:
                    return JsonResponse({'success': False, 'status': 404, 'message': 'Cámara no encontrada en la base de datos.'})
            else:
                ip = (data.get('ip') or '').strip()
                puerto_rtsp = int(data.get('puerto_rtsp') or 554)
                usuario = (data.get('usuario') or 'admin').strip()
                password = data.get('password', '')
                stream = (data.get('stream') or 'onvif2').strip()

            resultado = test_camera_connection(
                ip=ip,
                port=puerto_rtsp,
                user=usuario,
                password=password,
                stream=stream
            )
            return JsonResponse(resultado)
        except Exception as e:
            return JsonResponse({'success': False, 'status': -1, 'message': f'Error en prueba: {str(e)}'})

    return JsonResponse({'success': False, 'message': 'Método no permitido'})


@login_required
def escanear_camaras_ajax(request):
    """Escanea la red local y dispositivos físicos retornando todas las cámaras encontradas y las ya asignadas."""
    try:
        escanear_red = request.GET.get('escanear', '0') == '1'
        if escanear_red:
            resultado = scan_all_cameras()
        else:
            resultado = {'success': True, 'ip_cameras': [], 'webcams': []}
        # Obtener todas las cámaras ya registradas en la base de datos
        camaras_bd = list(ConfiguracionCamara.objects.all().order_by('id').values(
            'id', 'nombre', 'tipo', 'ip', 'puerto_onvif', 'puerto_rtsp', 
            'usuario', 'stream', 'webcam_index', 'activa'
        ))
        
        cam_activa = ConfiguracionCamara.get_activa()
        
        resultado['asignadas'] = camaras_bd
        resultado['activa_id'] = cam_activa.id if cam_activa else None
        return JsonResponse(resultado)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@login_required
def asignar_camara_ajax(request):
    """Asigna y guarda una cámara de forma persistente con nombre personalizado sin desasignar las demás."""
    if request.method == 'POST':
        try:
            import json
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST

            tipo = data.get('tipo', 'ip_yoosee')
            if tipo == 'ip':
                tipo = 'ip_yoosee'
            nombre = (data.get('nombre') or '').strip()
            if not nombre:
                nombre = 'Cámara IP' if tipo == 'ip_yoosee' else 'Webcam Local'
            ip = (data.get('ip') or '').strip()
            puerto_onvif = int(data.get('puerto_onvif') or 5000)
            puerto_rtsp = int(data.get('puerto_rtsp') or 554)
            usuario = (data.get('usuario') or 'admin').strip()
            password = (data.get('password') or 'admin12345').strip()
            stream = (data.get('stream') or 'onvif2').strip()
            webcam_index = int(data.get('webcam_index') or 0)

            # Buscar si ya existe para actualizar o crear nueva
            if tipo == 'ip_yoosee':
                cam = ConfiguracionCamara.objects.filter(ip=ip).first()
                if not cam:
                    cam = ConfiguracionCamara(ip=ip)
                cam.nombre = nombre
                cam.tipo = tipo
                cam.puerto_onvif = puerto_onvif
                cam.puerto_rtsp = puerto_rtsp
                cam.usuario = usuario
                if password:
                    cam.password = password
                cam.stream = stream
                cam.activa = True
                cam.save()
            else:
                cam = ConfiguracionCamara.objects.filter(tipo='webcam', webcam_index=webcam_index).first()
                if not cam:
                    cam = ConfiguracionCamara(tipo='webcam', webcam_index=webcam_index)
                cam.nombre = nombre
                cam.tipo = tipo
                cam.activa = True
                cam.save()

            # Reiniciar el worker específico de esta cámara
            get_shared_ip_camera(cam_id=cam.id, force_restart=True)

            return JsonResponse({
                'success': True,
                'message': f'Cámara "{cam.nombre}" asignada y guardada correctamente.',
                'camara': {
                    'id': cam.id,
                    'nombre': cam.nombre,
                    'tipo': cam.tipo,
                    'ip': cam.ip,
                    'webcam_index': cam.webcam_index,
                    'activa': cam.activa
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Método no permitido'})


@csrf_exempt
@login_required
def renombrar_camara_ajax(request):
    """Permite cambiar el nombre/ubicación asignado a una cámara existente."""
    if request.method == 'POST':
        try:
            import json
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST

            cam_id = data.get('id')
            nuevo_nombre = (data.get('nombre') or '').strip()

            if not cam_id or not nuevo_nombre:
                return JsonResponse({'success': False, 'error': 'ID y Nombre requeridos'})

            cam = ConfiguracionCamara.objects.filter(id=cam_id).first()
            if not cam:
                return JsonResponse({'success': False, 'error': 'Cámara no encontrada'})

            cam.nombre = nuevo_nombre
            cam.save(update_fields=['nombre', 'fecha_actualizacion'])

            return JsonResponse({
                'success': True,
                'message': f'Nombre actualizado a "{nuevo_nombre}".',
                'camara': {
                    'id': cam.id,
                    'nombre': cam.nombre
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Método no permitido'})


@csrf_exempt
@login_required
def eliminar_camara_ajax(request):
    """Desasigna y elimina una cámara registrada en la base de datos."""
    if request.method == 'POST':
        try:
            import json
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST

            cam_id = data.get('id')
            if not cam_id:
                return JsonResponse({'success': False, 'error': 'ID requerido'})

            cam = ConfiguracionCamara.objects.filter(id=cam_id).first()
            if cam:
                nombre = cam.nombre
                release_camera_instance(cam.id)
                cam.delete()
                return JsonResponse({'success': True, 'message': f'Cámara "{nombre}" desasignada correctamente.'})
            else:
                return JsonResponse({'success': False, 'error': 'Cámara no encontrada'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Método no permitido'})


@csrf_exempt
@login_required
def seleccionar_camara_ajax(request):
    """Establece una cámara como principal de monitoreo sin desactivar las demás."""
    if request.method == 'POST':
        try:
            import json
            try:
                data = json.loads(request.body)
            except Exception:
                data = request.POST

            cam_id = data.get('id')
            cam = ConfiguracionCamara.objects.filter(id=cam_id).first()
            if not cam:
                return JsonResponse({'success': False, 'error': 'Cámara no encontrada'})

            ConfiguracionCamara.objects.exclude(id=cam.id).update(activa=False)
            cam.activa = True
            cam.save()
            with _camera_lock:
                for k in list(_camera_instances.keys()):
                    if k != cam.id:
                        try:
                            _camera_instances[k].release()
                        except Exception:
                            pass
                        del _camera_instances[k]
            get_shared_ip_camera(cam_id=cam.id, force_restart=True)

            return JsonResponse({
                'success': True,
                'message': f'Cámara "{cam.nombre}" seleccionada para monitoreo.',
                'camara': {
                    'id': cam.id,
                    'nombre': cam.nombre,
                    'tipo': cam.tipo,
                    'ip': cam.ip
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Método no permitido'})


# ==========================================
# GESTIÓN DE PROTOCOLO LOCKDOWN (CIERRE PERIMETRAL)
# ==========================================
@login_required
def lockdown_estado_ajax(request):
    """Retorna el estado actual del Protocolo de Lockdown y el pase de lista de visitas."""
    lockdown = ProtocoloLockdown.get_activo()
    esta_activo = (lockdown is not None)

    visitas_en_recinto = []
    if esta_activo:
        from accesos.models import VisitaExterna
        qs_visitas = VisitaExterna.objects.filter(fecha_egreso__isnull=True).order_by('-fecha_ingreso')
        for v in qs_visitas:
            minutos = int((timezone.now() - v.fecha_ingreso).total_seconds() / 60) if v.fecha_ingreso else 0
            visitas_en_recinto.append({
                'id': v.id,
                'nombre': v.nombre_visitante,
                'rut': v.rut_visitante or 'S/RUT',
                'interno_a_visitar': v.interno_a_visitar or 'No especificado',
                'modulo': getattr(v, 'modulo_interno', 'General'),
                'minutos_en_recinto': minutos,
                'alerta_tiempo': v.tiempo_excedido,
            })

    return JsonResponse({
        'activo': esta_activo,
        'motivo': lockdown.motivo if lockdown else '',
        'origen': lockdown.get_origen_display() if lockdown else '',
        'fecha_activacion': lockdown.fecha_activacion.strftime('%H:%M:%S (%d/%m/%Y)') if lockdown else '',
        'visitas_en_recinto': visitas_en_recinto,
        'total_visitas_en_recinto': len(visitas_en_recinto)
    })


@csrf_exempt
@login_required
def lockdown_activar_ajax(request):
    """Activa el cierre perimetral total manualmente."""
    if request.method == 'POST':
        motivo = request.POST.get('motivo', 'Cierre Perimetral Táctico Activado por Operador').strip()
        lockdown = ProtocoloLockdown.activar(
            motivo=motivo or 'Cierre Perimetral Táctico Activado por Operador',
            origen='MANUAL_OPERADOR',
            usuario=request.user if request.user.is_authenticated else None
        )
        return JsonResponse({'status': 'ok', 'mensaje': 'Protocolo Lockdown activado exitosamente.', 'id': lockdown.id})
    return JsonResponse({'status': 'error', 'mensaje': 'Método no permitido'}, status=405)


@csrf_exempt
@login_required
def lockdown_desactivar_ajax(request):
    """Desactiva el cierre perimetral validando el PIN maestro."""
    if request.method == 'POST':
        codigo_pin = request.POST.get('pin', '').strip()
        observaciones = request.POST.get('observaciones', '').strip()
        exito, mensaje = ProtocoloLockdown.desactivar(
            codigo_pin=codigo_pin,
            usuario=request.user if request.user.is_authenticated else None,
            observaciones=observaciones
        )
        if exito:
            return JsonResponse({'status': 'ok', 'mensaje': mensaje})
        else:
            return JsonResponse({'status': 'error', 'mensaje': mensaje}, status=400)
    return JsonResponse({'status': 'error', 'mensaje': 'Método no permitido'}, status=405)
