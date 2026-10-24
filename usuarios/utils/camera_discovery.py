import os
import sys
import socket
import uuid
import time
import cv2

# Silenciar logs internos de OpenCV a nivel de librería
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

class SuppressStderr:
    """
    Context manager para silenciar temporalmente mensajes emitidos a bajo nivel por C/C++ (stderr),
    como los avisos de backend de OpenCV (DSHOW, obsensor, ffmpeg).
    """
    def __enter__(self):
        try:
            self.orig_fd = os.dup(2)
            self.devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(self.devnull, 2)
            self.redirected = True
        except Exception:
            self.redirected = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if getattr(self, 'redirected', False):
            try:
                os.dup2(self.orig_fd, 2)
                os.close(self.devnull)
                os.close(self.orig_fd)
            except Exception:
                pass


def discover_onvif_cameras(timeout=2.0):
    """
    Descubre cámaras IP ONVIF en la red local enviando un WS-Discovery Probe multicast.
    """
    message_id = f"urn:uuid:{uuid.uuid4()}"
    ws_probe = f"""<?xml version="1.0" encoding="utf-8"?>
<Envelope xmlns:dn="http://www.onvif.org/ver10/network/wsdl"
          xmlns="http://www.w3.org/2003/05/soap-envelope">
  <Header>
    <wsa:MessageID xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">{message_id}</wsa:MessageID>
    <wsa:To xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">urn:schemas-xmlsoap-org:ws:2005/04/discovery</wsa:To>
    <wsa:Action xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>
  </Header>
  <Body>
    <Probe xmlns="http://schemas.xmlsoap.org/ws/2005/04/discovery">
      <Types>dn:NetworkVideoTransmitter</Types>
    </Probe>
  </Body>
</Envelope>"""

    cameras = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(timeout)

    try:
        sock.sendto(ws_probe.encode('utf-8'), ('239.255.255.250', 3702))
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data, addr = sock.recvfrom(65536)
                ip = addr[0]
                text = data.decode('utf-8', errors='ignore')
                
                port_onvif = 5000
                if ':8899' in text: port_onvif = 8899
                elif ':8080' in text: port_onvif = 8080
                elif ':80/' in text or ':80 ' in text: port_onvif = 80
                elif ':5000' in text: port_onvif = 5000

                cameras.append({
                    'id': f'ip_{ip.replace(".", "_")}',
                    'tipo': 'ip_yoosee',
                    'nombre': f'Cámara IP ONVIF ({ip})',
                    'ip': ip,
                    'puerto_onvif': port_onvif,
                    'puerto_rtsp': 554,
                    'stream': 'onvif2',
                    'icono': '📡'
                })
            except socket.timeout:
                break
            except Exception:
                break
    except Exception as e:
        print(f"Error en WS-Discovery: {e}")
    finally:
        sock.close()

    # Deduplicar por IP
    unique_cams = {}
    for c in cameras:
        unique_cams[c['ip']] = c

    return list(unique_cams.values())


def get_windows_camera_names():
    """Obtiene los nombres amigables de cámaras en Windows (ej: Iriun Webcam)."""
    try:
        import subprocess
        cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -eq \'Camera\' -or $_.PNPClass -eq \'Image\' } | Select-Object -ExpandProperty Name"'
        output = subprocess.check_output(cmd, shell=True, text=True, timeout=2.5)
        return [l.strip() for l in output.splitlines() if l.strip()]
    except Exception:
        return []


def discover_local_webcams(max_devices=6):
    """
    Detecta webcams USB / virtuales (como Iriun Webcam) / integradas locales disponibles de manera segura,
    sin emitir advertencias de bajo nivel de OpenCV ni bloquear el escaneo.
    """
    friendly_names = get_windows_camera_names()
    found = []
    consecutive_failures = 0

    for idx in range(max_devices):
        cap = None
        try:
            with SuppressStderr():
                # En Windows probamos primero DirectShow (el backend nativo que usa Iriun)
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    try: cap.release()
                    except Exception: pass
                    # Si falla, probamos Microsoft Media Foundation (MSMF)
                    cap = cv2.VideoCapture(idx, cv2.CAP_MSMF)
                
                # Si fallan ambos backends específicos, probamos el predeterminado
                if not cap.isOpened():
                    try: cap.release()
                    except Exception: pass
                    cap = cv2.VideoCapture(idx)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    # Determinar nombre amigable real (ej: Iriun Webcam)
                    nombre_cam = friendly_names[idx] if (friendly_names and idx < len(friendly_names)) else f'Webcam Local #{idx}'
                    found.append({
                        'id': f'webcam_{idx}',
                        'tipo': 'webcam',
                        'nombre': nombre_cam,
                        'webcam_index': idx,
                        'icono': '💻'
                    })
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            else:
                consecutive_failures += 1
        except (cv2.error, Exception):
            consecutive_failures += 1
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

        # Si ya fallaron 3 dispositivos seguidos, no sondear más índices
        if consecutive_failures >= 3:
            break

    return found


def scan_all_cameras():
    """
    Escaneo integral de todas las cámaras IP en red local y webcams USB / virtuales.
    """
    ip_cameras = discover_onvif_cameras(timeout=1.8)
    webcams = discover_local_webcams(max_devices=6)
    return {
        'success': True,
        'ip_cameras': ip_cameras,
        'webcams': webcams,
        'total': len(ip_cameras) + len(webcams)
    }
