from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from usuarios.models import Persona, Acceso
from accesos.models import VisitaExterna


class VisitaExternaTestCase(TestCase):

    def setUp(self):
        self.persona = Persona.objects.create(
            nombre="Mariana",
            apellido="Rojas",
            rut="18.999.888-7",
            tipo_persona="visita",
            estado="activo"
        )

    def test_creacion_visita_en_recinto(self):
        """Verifica que una visita recién ingresada inicie en estado EN_RECINTO con temporizador activo."""
        visita = VisitaExterna.objects.create(
            persona=self.persona,
            nombre_visitante="Mariana Rojas",
            rut_visitante="18.999.888-7",
            interno_a_visitar="Pedro Morales",
            modulo_interno="Módulo C",
            parentesco_o_motivo="Hermana",
            estado="EN_RECINTO"
        )
        self.assertEqual(visita.estado, 'EN_RECINTO')
        self.assertFalse(visita.ha_egresado)
        self.assertFalse(visita.tiempo_excedido)
        self.assertGreater(visita.segundos_restantes, 10000)

    def test_egreso_visita_finalizada(self):
        """Verifica el cierre de visita y cálculo de permanencia reglamentaria."""
        hace_una_hora = timezone.now() - timedelta(hours=1)
        visita = VisitaExterna.objects.create(
            persona=self.persona,
            nombre_visitante="Mariana Rojas",
            rut_visitante="18.999.888-7",
            fecha_ingreso=hace_una_hora,
            estado="EN_RECINTO"
        )
        # Registrar egreso
        visita.fecha_egreso = timezone.now()
        visita.estado = "FINALIZADA"
        visita.puerta_egreso = "Acceso Principal [Egreso]"
        visita.save()

        self.assertTrue(visita.ha_egresado)
        self.assertEqual(visita.estado, "FINALIZADA")
        self.assertEqual(visita.segundos_restantes, 0)
