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

    # Imagen de respaldo en caso de que la cámara no esté accesible (ej. en la nube o apagada)
    fallback_img = None
    fallback_path = os.path.join(settings.BASE_DIR, 'camara_yoosee_live.jpg')
    if os.path.exists(fallback_path):
        fallback_img = cv2.imread(fallback_path)

    while True:
        cam = get_shared_ip_camera(cam_id=cam_pk)
        ret, frame = (False, None)
        if cam is not None:
            ret, frame = cam.get_latest_frame()

        if not ret or frame is None:
            # Enviar frame de espera/simulación informativo para no congelar el navegador
            if fallback_img is not None:
                frame = fallback_img.copy()
                cv2.putText(frame, f"[CONECTANDO: {nombre_cam}]", (15, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
                cv2.putText(frame, "Esperando flujo de video en red...", (15, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
            else:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, f"CAMARA: {nombre_cam}", (30, 220),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
                cv2.putText(frame, "Sin senal de video activa", (30, 260),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 2)

            _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
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

                # Registrar acceso en la BD (cooldown de 5 segundos por sujeto en esta cámara)
                registro_key = f"{persona.id if persona else 'desconocido'}_{cam_pk}"
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
                                camara=nombre_cam_registrado
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

                # Cooldown de 5 segundos por sujeto para no duplicar registros en la BD
                user_id = request.user.id if request.user.is_authenticated else 'anon'
                registro_key = f"{persona.id if persona else 'desconocido'}_{user_id}"
                nuevo_registro = False
                with _browser_cooldown_lock:
                    if registro_key not in _browser_cooldowns or (ahora - _browser_cooldowns[registro_key]) > 5.0:
                        _browser_cooldowns[registro_key] = ahora
                        nuevo_registro = True

                avatar_url = f"/media/secure/{persona.foto.name}" if (persona and persona.foto) else "/static/img/no-face.jpg"

                rostro_color = frame[y1:y2, x1:x2]
                if nuevo_registro and rostro_color.size > 0:
                    try:
                        _, buffer = cv2.imencode('.jpg', rostro_color)
                        enc_bytes = encrypt_bytes(buffer.tobytes())

                        acceso = Acceso.objects.create(
                            persona=persona,
                            nombre_detectado=nombre,
                            coincidencia=coincidencia,
                            resultado=estado,
                            camara=camara_nombre
                        )
                        foto_name = f"{uuid.uuid4()}.jpg"
                        acceso.foto_validacion.save(
                            foto_name,
                            ContentFile(enc_bytes),
                            save=True
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
                    'nuevo_registro': nuevo_registro
                })

            return JsonResponse({'rostros': resultados})
        except Exception as e:
            return JsonResponse({'rostros': [], 'error': str(e)})

    return JsonResponse({'rostros': []})


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
        items.append({
            'id': acc.id,
            'nombre': f"{acc.persona.nombre} {acc.persona.apellido}" if acc.persona else (acc.nombre_detectado or "Sujeto Desconocido"),
            'tipo': acc.persona.get_tipo_persona_display() if acc.persona else "Externo",
            'hora': acc.fecha_hora.strftime('%H:%M:%S') if acc.fecha_hora else "",
            'camara': acc.camara or "Cámara",
            'flujo': 'egreso' if es_egreso else 'ingreso',
            'resultado': acc.resultado,
            'coincidencia': round(acc.coincidencia, 0) if acc.coincidencia else 0,
            'foto_url': foto_url
        })
    return JsonResponse({'success': True, 'flujo': flujo, 'detecciones': items})


@login_required
def escanear_camaras_ajax(request):
    """Escanea la red local y dispositivos físicos retornando todas las cámaras encontradas y las ya asignadas."""
    try:
        resultado = scan_all_cameras()
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

            cam.activa = True
            cam.save()
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
