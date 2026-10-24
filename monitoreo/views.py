import os
import cv2
import base64
import numpy as np
import uuid
import threading
import time
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from usuarios.models import Acceso, Persona, ConfiguracionCamara
from django.contrib.auth.decorators import login_required
from usuarios.utils.security import encrypt_bytes
from usuarios.utils.deep_learning import DeepFaceEngine
from usuarios.utils.camera_discovery import scan_all_cameras
from facial_secure.ip_camera import YooseeIPCamera

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
# INSTANCIA SINGLETON DE CÁMARA (PERSISTENTE)
# ==========================================
_camera_singleton = None
_camera_lock = threading.Lock()

def get_shared_ip_camera(force_restart=False):
    """Obtiene o reinicia la instancia única de captura de video con la configuración activa."""
    global _camera_singleton
    with _camera_lock:
        if force_restart and _camera_singleton is not None:
            try:
                _camera_singleton.release()
            except Exception:
                pass
            _camera_singleton = None

        if _camera_singleton is None or not _camera_singleton.running:
            cfg = ConfiguracionCamara.get_activa()
            _camera_singleton = YooseeIPCamera(
                tipo=cfg.tipo,
                ip=cfg.ip,
                user=cfg.usuario,
                password=cfg.password,
                stream=cfg.stream,
                webcam_index=cfg.webcam_index
            )
    return _camera_singleton


def generar_stream_con_reconocimiento():
    """Generador continuo no-bloqueante con Inferencia Deep Learning SFace + YuNet."""
    engine = DeepFaceEngine.get_instance()
    ultimo_registro_tiempo = {}
    frame_count = 0

    # Carga inicial de embeddings
    get_cached_embeddings()

    while True:
        cam = get_shared_ip_camera()
        ret, frame = cam.get_latest_frame()
        if not ret or frame is None:
            time.sleep(0.04)
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

                try:
                    aligned_face, live_feat = engine.align_and_extract_feature(frame, face)
                    
                    if matrix is not None and len(personas_list) > 0 and live_feat is not None:
                        best_persona, score, coincidencia = engine.match_against_matrix(live_feat, matrix, personas_list)

                        if coincidencia >= 65.0:
                            persona = best_persona
                            permitido = (persona.estado == 'activo')
                            if permitido:
                                estado = 'PERMITIDO'
                                color_box = (0, 255, 0) # Verde
                            else:
                                estado = 'DENEGADO'
                                color_box = (0, 0, 255) # Rojo
                            label_text = f"{persona.nombre} {persona.apellido} ({coincidencia:.0f}%)"
                        elif coincidencia >= 45.0:
                            persona = best_persona
                            estado = 'REVISION'
                            color_box = (0, 165, 255) # Ámbar
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

                cv2.putText(frame, label_text, (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_box, 2)

                # Registrar acceso en la BD (cooldown de 5 segundos)
                registro_key = persona.id if persona else 'desconocido'
                if registro_key not in ultimo_registro_tiempo or (ahora - ultimo_registro_tiempo[registro_key]) > 5.0:
                    ultimo_registro_tiempo[registro_key] = ahora
                    try:
                        rostro_color = frame[y1:y2, x1:x2]
                        if rostro_color.size > 0:
                            _, buf = cv2.imencode('.jpg', rostro_color)
                            enc_bytes = encrypt_bytes(buf.tobytes())

                            acceso = Acceso.objects.create(
                                persona=persona,
                                nombre_detectado=persona.nombre if persona else "Sujeto Desconocido",
                                coincidencia=coincidencia,
                                resultado=estado,
                                camara="Cámara Principal (IP Yoosee)"
                            )
                            acceso.foto_validacion.save(
                                f"{uuid.uuid4()}.jpg",
                                ContentFile(enc_bytes),
                                save=True
                            )
                    except Exception as e:
                        print("Error registrando acceso:", e)

        # Codificar en JPEG a 25-30 FPS
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
        time.sleep(0.03)


@login_required
def video_feed(request):
    """Endpoint de transmisión en vivo MJPEG para Monitoreo y Dashboard."""
    return StreamingHttpResponse(
        generar_stream_con_reconocimiento(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


@login_required
def monitoreo(request):
    accesos = Acceso.objects.select_related('persona').order_by('-fecha_hora')[:20]
    return render(
        request,
        'monitoreo/monitoreo.html',
        {
            'accesos': accesos
        }
    )


@csrf_exempt
@login_required
def detectar_rostros(request):
    """Endpoint para detección e inferencia Deep Learning sobre fotogramas base64."""
    if request.method == 'POST':
        foto_base64 = request.POST.get('foto_base64')
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

            resultados = []

            for face in faces:
                fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                x1 = max(0, fx)
                y1 = max(0, fy)
                x2 = min(frame.shape[1], fx + fw)
                y2 = min(frame.shape[0], fy + fh)

                nombre = 'Desconocido'
                coincidencia = 0.0
                estado = 'REVISION'
                persona = None

                try:
                    aligned_face, live_feat = engine.align_and_extract_feature(frame, face)
                    if matrix is not None and len(personas_list) > 0 and live_feat is not None:
                        best_persona, score, coincidencia = engine.match_against_matrix(live_feat, matrix, personas_list)

                        if coincidencia >= 65.0:
                            persona = best_persona
                            permitido = (persona.estado == 'activo')
                            estado = 'PERMITIDO' if permitido else 'DENEGADO'
                            nombre = f"{persona.nombre} {persona.apellido}"
                        elif coincidencia >= 45.0:
                            persona = best_persona
                            estado = 'REVISION'
                            nombre = f"{persona.nombre} {persona.apellido}"
                        else:
                            estado = 'DENEGADO'
                            nombre = "Sujeto Desconocido"
                            persona = None
                except Exception as e:
                    print("Error en inferencia webcam:", e)

                rostro_color = frame[y1:y2, x1:x2]
                if rostro_color.size > 0:
                    _, buffer = cv2.imencode('.jpg', rostro_color)
                    enc_bytes = encrypt_bytes(buffer.tobytes())

                    acceso = Acceso.objects.create(
                        persona=persona,
                        nombre_detectado=nombre,
                        coincidencia=coincidencia,
                        resultado=estado,
                        camara='Camara Principal'
                    )
                    acceso.foto_validacion.save(
                        f"{uuid.uuid4()}.jpg",
                        ContentFile(enc_bytes),
                        save=True
                    )

                resultados.append({
                    'id': f'{fx}-{fy}-{fw}-{fh}',
                    'x': int(fx),
                    'y': int(fy),
                    'w': int(fw),
                    'h': int(fh),
                    'estado': estado,
                    'coincidencia': coincidencia,
                    'nombre': nombre,
                    'tipo': persona.get_tipo_persona_display() if persona else 'Desconocido',
                    'rut': persona.rut if persona else '---',
                    'hora': time.strftime('%H:%M:%S')
                })

            return JsonResponse({'rostros': resultados})
        except Exception as e:
            return JsonResponse({'rostros': [], 'error': str(e)})

    return JsonResponse({'rostros': []})


@login_required
def escanear_camaras_ajax(request):
    """Escanea la red local y dispositivos físicos retornando todas las cámaras encontradas."""
    try:
        resultado = scan_all_cameras()
        cam_activa = ConfiguracionCamara.get_activa()
        
        activa_dict = {
            'id': cam_activa.id,
            'nombre': cam_activa.nombre,
            'tipo': cam_activa.tipo,
            'ip': cam_activa.ip,
            'puerto_onvif': cam_activa.puerto_onvif,
            'puerto_rtsp': cam_activa.puerto_rtsp,
            'usuario': cam_activa.usuario,
            'stream': cam_activa.stream,
            'webcam_index': cam_activa.webcam_index
        }
        
        resultado['activa'] = activa_dict
        return JsonResponse(resultado)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@login_required
def seleccionar_camara_ajax(request):
    """Establece de forma persistente la cámara activa en la BD y reinicia la transmisión."""
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
            nombre = data.get('nombre', 'Cámara Principal')
            ip = data.get('ip', '192.168.100.34')
            puerto_onvif = int(data.get('puerto_onvif') or 5000)
            puerto_rtsp = int(data.get('puerto_rtsp') or 554)
            usuario = data.get('usuario', 'admin')
            password = data.get('password', 'admin12345')
            stream = data.get('stream', 'onvif2')
            webcam_index = int(data.get('webcam_index') or 0)

            # Desactivar todas las anteriores
            ConfiguracionCamara.objects.all().update(activa=False)

            # Guardar o actualizar la cámara activa
            if tipo == 'ip_yoosee':
                cam = ConfiguracionCamara.objects.filter(ip=ip).first()
                if not cam:
                    cam = ConfiguracionCamara(ip=ip)
                cam.nombre = nombre
                cam.tipo = tipo
                cam.puerto_onvif = puerto_onvif
                cam.puerto_rtsp = puerto_rtsp
                cam.usuario = usuario
                cam.password = password
                cam.stream = stream
                cam.activa = True
                cam.save()
            else:
                cam = ConfiguracionCamara.objects.filter(tipo='webcam', webcam_index=webcam_index).first()
                if not cam:
                    cam = ConfiguracionCamara(tipo='webcam', webcam_index=webcam_index)
                cam.nombre = nombre
                cam.activa = True
                cam.save()

            # Reiniciar inmediatamente el worker singleton
            get_shared_ip_camera(force_restart=True)

            return JsonResponse({
                'success': True,
                'message': f'Cámara "{cam.nombre}" activada exitosamente como principal.',
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
