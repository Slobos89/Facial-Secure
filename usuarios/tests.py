from django.test import TestCase, Client
from django.contrib.auth.models import User
from usuarios.models import Persona, PerfilUsuario, HuellaDactilar


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

