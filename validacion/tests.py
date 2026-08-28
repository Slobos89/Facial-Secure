import base64
import json
import struct
from django.test import TestCase, Client
from django.contrib.auth.models import User
from usuarios.models import Persona, HuellaDactilar, Acceso, PerfilUsuario
from usuarios.utils.biometria_dactilar import comparar_templates_huella, parse_ansi378_minutiae


def crear_dummy_ansi378(minucias=[(100, 150, 45, 1, 80), (200, 250, 90, 2, 85), (300, 350, 135, 1, 90), (400, 450, 180, 2, 75)]):
    """Genera un template binario sintético ANSI-378 para pruebas."""
    header = b'FMR\x00' + b'\x00' * 20
    body = bytearray()
    for (x, y, theta_deg, tipo, cal) in minucias:
        val_x = (tipo << 14) | (x & 0x3FFF)
        val_y = y & 0x3FFF
        angulo = int(theta_deg * (256.0 / 360.0)) & 0xFF
        body += struct.pack('>HHBB', val_x, val_y, angulo, cal)
    return base64.b64encode(header + bytes(body)).decode('ascii')


class BiometriaDactilarTestCase(TestCase):

    def setUp(self):
        self.template_a = crear_dummy_ansi378([
            (100, 150, 45, 1, 80),
            (200, 250, 90, 2, 85),
            (300, 350, 135, 1, 90),
            (400, 450, 180, 2, 75)
        ])

        # Template A con ligera variación (mismo dedo)
        self.template_a_similar = crear_dummy_ansi378([
            (102, 151, 46, 1, 80),
            (201, 248, 88, 2, 85),
            (298, 352, 137, 1, 90),
            (403, 449, 178, 2, 75)
        ])

        # Template B (dedo completamente diferente)
        self.template_b = crear_dummy_ansi378([
            (800, 900, 10, 1, 80),
            (1200, 1300, 50, 2, 85),
            (1500, 1600, 120, 1, 90),
            (1700, 1800, 200, 2, 75)
        ])

        self.persona = Persona.objects.create(
            nombre="Carlos",
            apellido="Valenzuela",
            rut="12.345.678-9",
            tipo_persona="interno",
            estado="activo"
        )

        self.huella = HuellaDactilar.objects.create(
            persona=self.persona,
            template=self.template_a,
            calidad=85,
            formato="ANSI378"
        )

        self.acceso = Acceso.objects.create(
            persona=self.persona,
            nombre_detectado="Carlos Valenzuela",
            camara="Camara Principal",
            coincidencia=58.0,
            resultado="REVISION",
            resuelto=False
        )

        self.client = Client()

    def test_matching_mismo_template_exacto(self):
        """Verifica que el mismo template tenga 100% de match."""
        res = comparar_templates_huella(self.template_a, self.template_a)
        self.assertTrue(res['match'])
        self.assertEqual(res['score'], 100.0)

    def test_matching_template_similar(self):
        """Verifica que dos lecturas del mismo dedo coincidan superando el umbral."""
        res = comparar_templates_huella(self.template_a, self.template_a_similar, umbral_coincidencia=70.0)
        self.assertTrue(res['match'])
        self.assertGreaterEqual(res['score'], 70.0)

    def test_matching_template_diferente(self):
        """Verifica que dos dedos distintos no coincidan."""
        res = comparar_templates_huella(self.template_a, self.template_b, umbral_coincidencia=70.0)
        self.assertFalse(res['match'])
        self.assertLess(res['score'], 50.0)

    def test_endpoint_validar_huella_acceso_exitoso(self):
        """Prueba endpoint POST /validacion/validar-huella/ con match positivo."""
        response = self.client.post(
            '/validacion/validar-huella/',
            data=json.dumps({
                'acceso_id': self.acceso.id,
                'template': self.template_a_similar,
                'calidad': 85
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['match'])
        self.assertEqual(data['estado'], 'APROBADO_MANUAL')

        self.acceso.refresh_from_db()
        self.assertEqual(self.acceso.resultado, 'APROBADO_MANUAL')
        self.assertTrue(self.acceso.resuelto)

    def test_endpoint_validar_huella_acceso_rechazado(self):
        """Prueba endpoint POST /validacion/validar-huella/ con huella no coincidente."""
        response = self.client.post(
            '/validacion/validar-huella/',
            data=json.dumps({
                'acceso_id': self.acceso.id,
                'template': self.template_b,
                'calidad': 80
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['match'])
        self.assertIn("NO coincide", data['mensaje'])
