import os
import sys
import urllib.request
import django

print("=" * 60)
print("     FACIAL SECURE - ASISTENTE DE CONFIGURACION TOTAL")
print("=" * 60)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Carpetas de Almacenamiento
print("\n[1/5] Verificando estructura de carpetas...")
carpetas = [
    os.path.join(BASE_DIR, 'media'),
    os.path.join(BASE_DIR, 'media', 'rostros'),
    os.path.join(BASE_DIR, 'media', 'rostros_dataset'),
    os.path.join(BASE_DIR, 'media', 'rostros_recortados'),
    os.path.join(BASE_DIR, 'media', 'secure'),
    os.path.join(BASE_DIR, 'media', 'validaciones'),
    os.path.join(BASE_DIR, 'modelo')
]
for c in carpetas:
    os.makedirs(c, exist_ok=True)
print("-> Todas las carpetas requeridas estan listas.")

# 2. Modelos Deep Learning ONNX
print("\n[2/5] Verificando modelos de Redes Neuronales (Deep Learning)...")
model_dir = os.path.join(BASE_DIR, 'modelo')
models = {
    'face_detection_yunet_2023mar.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
    'face_recognition_sface_2021dec.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'
}
for name, url in models.items():
    path = os.path.join(model_dir, name)
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        print(f"Descargando {name}...")
        urllib.request.urlretrieve(url, path)
        print(f"-> {name} descargado ({os.path.getsize(path)/1024:.1f} KB).")
    else:
        print(f"-> {name} ya presente ({os.path.getsize(path)/1024:.1f} KB).")

# 3. Creacion de Base de Datos PostgreSQL si no existe
print("\n[3/5] Verificando Base de Datos PostgreSQL...")
try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    from django.conf import settings
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facial_secure.settings')
    
    # Extraer credenciales de settings
    from facial_secure import settings as app_settings
    db_conf = app_settings.DATABASES['default']
    
    conn = psycopg2.connect(
        dbname='postgres',
        user=db_conf['USER'],
        password=db_conf['PASSWORD'],
        host=db_conf['HOST'],
        port=db_conf['PORT']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_conf['NAME'],))
    exists = cur.fetchone()
    if not exists:
        cur.execute(f"CREATE DATABASE {db_conf['NAME']};")
        print(f"-> Base de datos '{db_conf['NAME']}' creada exitosamente en PostgreSQL.")
    else:
        print(f"-> Base de datos '{db_conf['NAME']}' confirmada en PostgreSQL.")
    cur.close()
    conn.close()
except Exception as e:
    print(f"-> [Aviso PostgreSQL]: {e}")

# 4. Migraciones Django
print("\n[4/5] Aplicando migraciones de la Base de Datos...")
try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facial_secure.settings')
    django.setup()
    from django.core.management import call_command
    call_command('migrate', interactive=False)
    print("-> Migraciones aplicadas exitosamente.")
except Exception as e:
    print(f"-> [Error en migraciones]: {e}")

# 5. Configuracion inicial de Camara
print("\n[5/5] Verificando configuracion activa de camaras...")
try:
    from usuarios.models import ConfiguracionCamara
    cam = ConfiguracionCamara.get_activa()
    print(f"-> Camara configurada: {cam.nombre} [{cam.tipo}]")
except Exception as e:
    print(f"-> [Aviso camaras]: {e}")

print("\n" + "=" * 60)
print("        SISTEMA CONFIGURADO Y LISTO PARA USAR")
print("=" * 60)
