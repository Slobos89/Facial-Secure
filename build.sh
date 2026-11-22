#!/usr/bin/env bash
# Salir si ocurre cualquier error
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facial_secure.settings')
django.setup()
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@facialsecure.cl', 'Admin1234!')
    print('Superusuario admin creado con éxito')
else:
    print('Superusuario admin ya existe')

from usuarios.models import ConfiguracionCamara
# Limpiar y desactivar cualquier cámara IP privada en la nube para evitar bloqueos
ConfiguracionCamara.objects.filter(ip__startswith='192.168.').update(activa=False)
ConfiguracionCamara.objects.filter(tipo__in=['ip_yoosee', 'ip_camera']).update(activa=False)
cam_webcam = ConfiguracionCamara.objects.filter(tipo='webcam').first()
if not cam_webcam:
    cam_webcam = ConfiguracionCamara.objects.create(
        nombre='Webcam Local (Dispositivo #0)',
        tipo='webcam',
        webcam_index=0,
        activa=True
    )
else:
    cam_webcam.activa = True
    cam_webcam.save()
print('Configuración de cámaras saneada: Webcam Local establecida como activa por defecto.')
"