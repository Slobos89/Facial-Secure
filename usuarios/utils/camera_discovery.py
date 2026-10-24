import os
import sys
import socket
import uuid
import time
import re
import hashlib
from concurrent.futures import ThreadPoolExecutor
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


PRIMARY_CAMERA_PORTS = [554, 5000, 8899, 8000, 8080, 10554]


def get_local_subnets():
    """Obtiene los prefijos de subredes IPv4 locales (ej: ['192.168.100'])."""
    subnets = set()
    try:
        host_name = socket.gethostname()
        for ip in socket.gethostbyname_ex(host_name)[2]:
            if not ip.startswith('127.') and ':' not in ip:
                parts = ip.split('.')
                if len(parts) == 4:
                    subnets.add(f"{parts[0]}.{parts[1]}.{parts[2]}")
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split('.')
        if len(parts) == 4:
            subnets.add(f"{parts[0]}.{parts[1]}.{parts[2]}")
    except Exception:
        pass

    if not subnets:
        subnets.add('192.168.1')
        subnets.add('192.168.0')
        subnets.add('192.168.100')

    return list(subnets)


def discover_onvif_cameras(timeout=1.5):
    """
    Descubre cámaras IP ONVIF en la red local enviando un WS-Discovery Probe multicast (239.255.255.250:3702).
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
                    'icono': '📡',
                    'metodo_descubrimiento': 'WS-Discovery (ONVIF)'
                })
            except socket.timeout:
                break
            except Exception:
                break
    except Exception as e:
        print(f"WS-Discovery aviso: {e}")
    finally:
        sock.close()

    unique_cams = {}
    for c in cameras:
        unique_cams[c['ip']] = c

    return list(unique_cams.values())


def probe_single_ip(ip):
    """
    Sondea rápidamente si una dirección IP tiene puertos de cámaras IP / RTSP / ONVIF abiertos.
    """
    open_ports = []
    for port in PRIMARY_CAMERA_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.18)
        try:
            if s.connect_ex((ip, port)) == 0:
                open_ports.append(port)
        except Exception:
            pass
        finally:
            try: s.close()
            except Exception: pass

    if not open_ports:
        return None

    # Si tiene 554 (RTSP) o 5000 / 8899 (ONVIF), es con seguridad un dispositivo de video
    onvif_port = 5000
    if 8899 in open_ports:
        onvif_port = 8899
    elif 5000 in open_ports:
        onvif_port = 5000
    elif 8080 in open_ports:
        onvif_port = 8080

    return {
        'id': f'ip_{ip.replace(".", "_")}',
        'tipo': 'ip_yoosee',
        'nombre': f'Cámara Wi-Fi / IP ({ip})',
        'ip': ip,
        'puerto_onvif': onvif_port,
        'puerto_rtsp': 554 if 554 in open_ports else open_ports[0],
        'stream': 'onvif2',
        'icono': '📡',
        'puertos_detectados': open_ports,
        'metodo_descubrimiento': 'Escaneo TCP Subred LAN/Wi-Fi'
    }


def discover_subnet_cameras(max_workers=90):
    """
    Escaneo multi-hilo de alta velocidad a través de la subred local (Wi-Fi o Cable)
    para detectar cámaras que tengan bloqueado el broadcast multicast de ONVIF por el router.
    """
    subnets = get_local_subnets()
    found = []
    for base in subnets:
        ips = [f"{base}.{i}" for i in range(1, 255)]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for r in executor.map(probe_single_ip, ips):
                if r:
                    found.append(r)
    return found


def test_camera_connection(ip, port=554, user='admin', password='', stream='onvif2', timeout=2.5):
    """
    Prueba en tiempo real si una cámara IP / Wi-Fi responde por RTSP y si las credenciales son válidas.
    Soporta autenticación estándar RTSP Digest (RFC 2069/2617) y Basic de forma ultrarrápida sin bloquear hilos.
    """
    ip = (ip or '').strip()
    port = int(port or 554)
    user = (user or 'admin').strip()
    password = password if password is not None else ''
    stream = (stream or 'onvif2').strip().lstrip('/')

    if not ip:
        return {'success': False, 'status': 0, 'message': 'Dirección IP no especificada.'}

    uri = f"rtsp://{ip}:{port}/{stream}"

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        
        # 1. Enviar solicitud inicial DESCRIBE
        req1 = f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\nUser-Agent: FacialSecure/1.0\r\n\r\n"
        s.sendall(req1.encode('utf-8'))
        res1 = s.recv(4096).decode('utf-8', errors='ignore')
        
        # Si responde 200 OK directamente, no requiere autenticación
        if '200 OK' in res1:
            s.close()
            return {
                'success': True,
                'status': 200,
                'message': '¡Conexión exitosa! La cámara responde y transmite sin clave.'
            }
            
        # Si no responde 401, verificar qué código devolvió
        if '401' not in res1:
            s.close()
            first_line = res1.splitlines()[0] if res1 else 'Sin respuesta'
            if '404' in res1:
                return {
                    'success': False,
                    'status': 404,
                    'message': f'Ruta /{stream} no existe (404 Not Found). Prueba con "onvif1" o "onvif2".'
                }
            return {
                'success': False,
                'status': 0,
                'message': f'Respuesta de la cámara: {first_line}'
            }
            
        # 2. Cámara solicitó autenticación 401 Unauthorized
        auth_line = ''
        for line in res1.splitlines():
            if line.lower().startswith('www-authenticate:'):
                auth_line = line
                break
                
        if not auth_line:
            s.close()
            return {
                'success': False,
                'status': 401,
                'message': 'La cámara requiere clave de acceso pero no especificó formato.'
            }
            
        realm_m = re.search(r'realm="([^"]+)"', auth_line, re.IGNORECASE)
        nonce_m = re.search(r'nonce="([^"]+)"', auth_line, re.IGNORECASE)
        
        realm = realm_m.group(1) if realm_m else 'HIipCamera'
        nonce = nonce_m.group(1) if nonce_m else ''
        
        # Calcular hash Digest MD5
        ha1 = hashlib.md5(f"{user}:{realm}:{password}".encode('utf-8')).hexdigest()
        ha2 = hashlib.md5(f"DESCRIBE:{uri}".encode('utf-8')).hexdigest()
        resp_hash = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode('utf-8')).hexdigest()
        
        auth_hdr = f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{resp_hash}"'
        req2 = f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 2\r\nAuthorization: {auth_hdr}\r\nAccept: application/sdp\r\nUser-Agent: FacialSecure/1.0\r\n\r\n"
        s.sendall(req2.encode('utf-8'))
        res2 = s.recv(4096).decode('utf-8', errors='ignore')
        s.close()
        
        if '200 OK' in res2:
            return {
                'success': True,
                'status': 200,
                'message': '¡Conexión y credenciales verificadas con éxito! Video listo para transmitir.'
            }
        elif '401' in res2 or '400' in res2:
            return {
                'success': False,
                'status': 401,
                'message': 'Contraseña incorrecta (Error de Autenticación). Verifica la clave configurada en la App de la cámara.'
            }
        elif '404' in res2:
            return {
                'success': False,
                'status': 404,
                'message': f'Canal /{stream} no encontrado (404 Not Found). Prueba cambiar el canal a onvif1.'
            }
        else:
            first_line = res2.splitlines()[0] if res2 else 'Sin respuesta'
            return {
                'success': False,
                'status': 0,
                'message': f'Respuesta de la cámara: {first_line}'
            }
            
    except socket.timeout:
        return {
            'success': False,
            'status': -1,
            'message': f'Tiempo de espera agotado al conectar a {ip}:{port}. Verifica que la cámara esté encendida y en la misma red Wi-Fi.'
        }
    except ConnectionRefusedError:
        return {
            'success': False,
            'status': -2,
            'message': f'Conexión rechazada en {ip}:{port}. El puerto RTSP está cerrado o la IP es incorrecta.'
        }
    except Exception as e:
        return {
            'success': False,
            'status': -3,
            'message': f'Error de red: {str(e)}'
        }


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
    Escaneo integral de todas las cámaras IP en red local (híbrido WS-Discovery ONVIF + sondeo TCP subred)
    y webcams USB / virtuales del equipo.
    """
    # 1. Escaneo concurrente de red IP
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_onvif = executor.submit(discover_onvif_cameras, timeout=1.5)
        f_subnet = executor.submit(discover_subnet_cameras)
        
        onvif_cams = f_onvif.result()
        subnet_cams = f_subnet.result()

    # Deduplicar cámaras IP por dirección IP
    unique_ip_cams = {}
    for cam in onvif_cams:
        unique_ip_cams[cam['ip']] = cam
        
    for cam in subnet_cams:
        if cam['ip'] not in unique_ip_cams:
            unique_ip_cams[cam['ip']] = cam
        else:
            # Preservar puertos adicionales si se encontraron
            if 'puertos_detectados' in cam:
                unique_ip_cams[cam['ip']]['puertos_detectados'] = cam['puertos_detectados']

    ip_cameras = list(unique_ip_cams.values())

    # 2. Escaneo de webcams locales
    webcams = discover_local_webcams(max_devices=6)

    return {
        'success': True,
        'ip_cameras': ip_cameras,
        'webcams': webcams,
        'total': len(ip_cameras) + len(webcams)
    }
