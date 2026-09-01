import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'facial_secure.settings')
django.setup()

from usuarios.utils.reconocimiento import entrenar_modelo

if __name__ == '__main__':
    print("\n[FACIAL SECURE] Ejecutando entrenamiento incremental y limpieza Zero-Knowledge...")
    entrenar_modelo()
    print("[FACIAL SECURE] Proceso finalizado con exito.\n")