import numpy as np
from django.test import TestCase, Client
from django.contrib.auth.models import User
from usuarios.models import Persona, PerfilUsuario, HuellaDactilar, Acceso


class UsuariosViewsTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='admin_test',
            password='password123'
        )
        self.client.login(username='admin_test', password='password123')

        self.persona = Persona.objects.create(
            nombre="Juan",
            apellido="Perez",
            rut="11.222.333-4",
            tipo_persona="gendarme",
            estado="activo"
        )

    def test_crear_persona_get_render(self):
        """Verifica que /usuarios/nuevo/ renderice correctamente con el tag static."""
        response = self.client.get('/usuarios/nuevo/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nuevo Enrolamiento Biométrico')
        self.assertContains(response, 'secugen.js')

    def test_editar_usuario_get_render(self):
        """Verifica que /usuarios/editar-usuario/<id>/ renderice correctamente."""
        response = self.client.get(f'/usuarios/editar-usuario/{self.persona.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Editar Usuario')
        self.assertContains(response, 'secugen.js')


class BiometriaFacialYAntiPassbackTestCase(TestCase):

    def setUp(self):
        self.persona = Persona.objects.create(
            nombre="Eduardo",
            apellido="Fuentes",
            rut="15.432.876-5",
            tipo_persona="visita",
            estado="activo"
        )

    def test_calculo_similitud_coseno_vector_128d(self):
        """Verifica comparación vectorial de embeddings SFace de 128 dimensiones."""
        vec_base = np.random.randn(128).astype(np.float32)
        vec_base /= np.linalg.norm(vec_base)

        # Mismo vector: similitud matemática 1.0
        sim_identica = float(np.dot(vec_base, vec_base))
        self.assertAlmostEqual(sim_identica, 1.0, places=4)

        # Vector con leve variación (ruido gaussiano)
        ruido = np.random.normal(0, 0.05, 128).astype(np.float32)
        vec_similar = (vec_base + ruido)
        vec_similar /= np.linalg.norm(vec_similar)
        sim_similar = float(np.dot(vec_base, vec_similar))
        self.assertGreater(sim_similar, 0.75)

    def test_regla_secuencial_anti_passback(self):
        """Verifica que el método esta_dentro_del_recinto valide la secuencia lógica Ingreso -> Egreso."""
        # 1. Al inicio, la persona no está dentro del recinto
        self.assertFalse(self.persona.esta_dentro_del_recinto())

        # 2. Se registra un INGRESO
        Acceso.objects.create(
            persona=self.persona,
            nombre_detectado="Eduardo Fuentes",
            camara="Camara Portico Ingreso",
            coincidencia=95.4,
            resultado="PERMITIDO"
        )
        self.assertTrue(self.persona.esta_dentro_del_recinto())

        # 3. Se registra un EGRESO posterior
        Acceso.objects.create(
            persona=self.persona,
            nombre_detectado="Eduardo Fuentes",
            camara="Camara Portico Egreso",
            coincidencia=93.8,
            resultado="PERMITIDO"
        )
        self.assertFalse(self.persona.esta_dentro_del_recinto())
