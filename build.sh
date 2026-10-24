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
"