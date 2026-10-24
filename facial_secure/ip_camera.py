import socket
import threading
import time
import cv2
import os
from usuarios.utils.camera_discovery import SuppressStderr


class YooseeIPCamera:
    """
    Controlador de video en tiempo real de ALTA DISPONIBILIDAD para Cámaras IP (ONVIF/H.265)
    y Webcams Locales USB con captura desacoplada en segundo plano (Producer-Consumer).
    """
    def __init__(self, tipo="ip_yoosee", ip="192.168.100.34", user="admin", password="admin12345", proxy_port=8554, stream="onvif2", webcam_index=0):
        self.tipo = tipo
        self.ip = ip or "192.168.100.34"
        self.user = user or "admin"
        self.password = password or "admin12345"
        self.proxy_port = proxy_port
        self.stream = stream or "onvif2"
        self.webcam_index = int(webcam_index or 0)
        
        self.proxy_server = None
        self.running = True
        
        self.last_frame = None
        self.last_frame_time = 0
        self.frame_lock = threading.Lock()
        self.active_cap = None
        
        if self.tipo == 'ip_yoosee':
            self._start_relay_proxy()
            self.worker_thread = threading.Thread(target=self._capture_worker_ip, daemon=True)
        else:
            self.worker_thread = threading.Thread(target=self._capture_worker_webcam, daemon=True)

        self.worker_thread.start()

    def _start_relay_proxy(self):
        try:
            self.proxy_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.proxy_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port_to_try = self.proxy_port if (self.proxy_port and self.proxy_port > 0) else 0
            try:
                self.proxy_server.bind(("127.0.0.1", port_to_try))
            except OSError:
                self.proxy_server.bind(("127.0.0.1", 0))
            self.proxy_port = self.proxy_server.getsockname()[1]
            self.proxy_server.listen(5)
            threading.Thread(target=self._proxy_loop, daemon=True).start()
            time.sleep(0.3)
        except Exception as e:
            print(f"[YooseeIPCamera] Error en proxy: {e}")

    def _proxy_loop(self):
        while self.running:
            try:
                client_sock, _ = self.proxy_server.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except:
                break

    def _handle_client(self, client_sock):
        try:
            camera_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            camera_sock.settimeout(4.0)
            camera_sock.connect((self.ip, 554))
        except Exception:
            try:
                client_sock.close()
            except:
                pass
            return

        def forward(src, dst, fix_header=False):
            try:
                while self.running:
                    data = src.recv(65536)
                    if not data:
                        break
                    if fix_header and b"Transport: RTP/AVP;" in data and b"interleaved=" in data:
                        data = data.replace(b"Transport: RTP/AVP;", b"Transport: RTP/AVP/TCP;")
                    dst.sendall(data)
            except:
                pass
            finally:
                try: src.close()
                except: pass
                try: dst.close()
                except: pass

        threading.Thread(target=forward, args=(client_sock, camera_sock, False), daemon=True).start()
        threading.Thread(target=forward, args=(camera_sock, client_sock, True), daemon=True).start()

    def _capture_worker_ip(self):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;500000|probesize;500000|fflags;nobuffer|flags;low_delay"
        url = f"rtsp://{self.user}:{self.password}@127.0.0.1:{self.proxy_port}/{self.stream}"
        
        while self.running:
            print(f"[YooseeIPCamera] Conectando worker a stream IP ({self.ip}/{self.stream})...")
            cap = None
            try:
                cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                with self.frame_lock:
                    self.active_cap = cap
                
                consecutive_failures = 0
                
                while self.running and cap.isOpened():
                    try:
                        ret = cap.grab()
                        if ret:
                            ret_frame, frame = cap.retrieve()
                            if ret_frame and frame is not None and frame.size > 0:
                                with self.frame_lock:
                                    self.last_frame = frame
                                    self.last_frame_time = time.time()
                                consecutive_failures = 0
                            else:
                                consecutive_failures += 1
                        else:
                            consecutive_failures += 1
                    except (cv2.error, Exception) as stream_err:
                        print(f"[YooseeIPCamera] Error en captura RTSP: {stream_err}")
                        consecutive_failures += 1
                    
                    if consecutive_failures > 35:
                        print("[YooseeIPCamera] Pérdida de señal RTSP. Reconectando...")
                        break
                    
                    time.sleep(0.015)
            except (cv2.error, Exception) as e:
                print(f"[YooseeIPCamera] Excepción en conexión IP: {e}")
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                with self.frame_lock:
                    self.active_cap = None
            
            if self.running:
                time.sleep(1.0)

    def _capture_worker_webcam(self):
        while self.running:
            print(f"[YooseeIPCamera] Abriendo webcam local #{self.webcam_index}...")
            cap = None
            try:
                with SuppressStderr():
                    cap = cv2.VideoCapture(self.webcam_index, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        try: cap.release()
                        except Exception: pass
                        cap = cv2.VideoCapture(self.webcam_index, cv2.CAP_MSMF)
                    if not cap.isOpened():
                        try: cap.release()
                        except Exception: pass
                        cap = cv2.VideoCapture(self.webcam_index)
                
                with self.frame_lock:
                    self.active_cap = cap
                
                if not cap.isOpened():
                    print(f"[YooseeIPCamera] Webcam #{self.webcam_index} no disponible o bloqueada. Reintentando...")
                    time.sleep(2.0)
                    continue
                
                while self.running and cap.isOpened():
                    try:
                        ret, frame = cap.read()
                        if ret and frame is not None and frame.size > 0:
                            with self.frame_lock:
                                self.last_frame = frame
                                self.last_frame_time = time.time()
                        else:
                            time.sleep(0.05)
                    except (cv2.error, Exception) as read_err:
                        print(f"[YooseeIPCamera] Error leyendo fotograma webcam: {read_err}")
                        time.sleep(0.1)
                        break
                    time.sleep(0.02)
            except (cv2.error, Exception) as e:
                print(f"[YooseeIPCamera] Excepción abriendo webcam #{self.webcam_index}: {e}")
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                with self.frame_lock:
                    self.active_cap = None
            
            if self.running:
                time.sleep(1.0)

    def get_latest_frame(self, max_age_seconds=2.5):
        """Retorna instantáneamente el último frame válido en memoria de forma thread-safe."""
        with self.frame_lock:
            if self.last_frame is not None and (time.time() - self.last_frame_time) <= max_age_seconds:
                return True, self.last_frame.copy()
        return False, None

    def release(self):
        self.running = False
        with self.frame_lock:
            if self.active_cap is not None:
                try:
                    self.active_cap.release()
                except Exception:
                    pass
                self.active_cap = None
            self.last_frame = None
            self.last_frame_time = 0
        if self.proxy_server:
            try:
                self.proxy_server.close()
            except Exception:
                pass
