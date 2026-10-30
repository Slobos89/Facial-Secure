from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class VisitaExterna(models.Model):
    """
    Registro y control de aforo para personas externas (visitas, abogados, proveedores).
    Permite el balance estricto de entradas vs salidas y auditoría biométrica/IA
    de vestimenta para prevenir intercambio de ropas o suplantaciones con internos.
    """
    ESTADOS_VISITA = [
        ('EN_RECINTO', 'En Recinto (Pendiente de Salida)'),
        ('FINALIZADA', 'Finalizada (Egresó - Conforme)'),
        ('ALERTA_DISCREPANCIA', 'Alerta: Discrepancia de Vestimenta'),
        ('OBSERVADA', 'Revisión Manual Requerida'),
    ]

    persona = models.ForeignKey(
        'usuarios.Persona',
        on_delete=models.SET_NULL,
        related_name='visitas_externas',
        null=True,
        blank=True,
        help_text="Enlace si la persona externa ya está enrolada en el sistema"
    )

    nombre_visitante = models.CharField(max_length=150, help_text="Nombre completo del visitante")
    rut_visitante = models.CharField(max_length=50, blank=True, null=True, help_text="RUT o documento de identidad")
    telefono = models.CharField(max_length=30, blank=True, default="")
    interno_a_visitar = models.CharField(max_length=150, blank=True, default="", help_text="Interno al cual acude a visitar")
    parentesco_o_motivo = models.CharField(max_length=100, blank=True, default="Visita general", help_text="Ej: Cónyuge, Abogado, Familiar")

    # Registro de Ingreso
    fecha_ingreso = models.DateTimeField(default=timezone.now, db_index=True)
    puerta_ingreso = models.CharField(max_length=100, default='Acceso Principal [Ingreso]')
    foto_ingreso = models.ImageField(upload_to='visitas/ingresos/', blank=True, null=True)
    acceso_ingreso = models.ForeignKey(
        'usuarios.Acceso',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visita_ingreso'
    )

    # Registro de Pertenencias y Vestimenta al Ingreso
    prenda_superior = models.CharField(max_length=150, blank=True, default="", help_text="Ej: Polera manga corta, chaqueta")
    color_superior = models.CharField(max_length=60, blank=True, default="", help_text="Ej: Azul marino, Rojo, Blanco")
    prenda_inferior = models.CharField(max_length=150, blank=True, default="", help_text="Ej: Pantalón jeans, buzo")
    color_inferior = models.CharField(max_length=60, blank=True, default="", help_text="Ej: Negro, Denim oscuro")
    calzado = models.CharField(max_length=100, blank=True, default="", help_text="Ej: Zapatillas blancas, botas")
    pertenencias_declaradas = models.TextField(blank=True, default="", help_text="Objetos que porta (mochila, cartera, abrigo, reloj, etc.)")
    descripcion_general = models.TextField(blank=True, default="", help_text="Detalle descriptivo de rasgos o atuendo general")

    # Registro de Egreso
    fecha_egreso = models.DateTimeField(null=True, blank=True, db_index=True)
    puerta_egreso = models.CharField(max_length=100, blank=True, default="")
    foto_egreso = models.ImageField(upload_to='visitas/egresos/', blank=True, null=True)
    acceso_egreso = models.ForeignKey(
        'usuarios.Acceso',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visita_egreso'
    )

    # Evaluación con Inteligencia Artificial (Comparación de Vestimenta)
    estado = models.CharField(max_length=30, choices=ESTADOS_VISITA, default='EN_RECINTO', db_index=True)
    similitud_vestimenta = models.FloatField(default=0.0, help_text="Porcentaje global de coincidencia (0-100%)")
    coincidencia_superior = models.FloatField(default=0.0, help_text="Coincidencia en prenda superior (%)")
    coincidencia_inferior = models.FloatField(default=0.0, help_text="Coincidencia en prenda inferior (%)")
    alerta_vestimenta = models.BooleanField(default=False, help_text="Indica si hubo discordancia sospechosa de ropa")
    dictamen_ia = models.TextField(blank=True, default="")

    # Auditoría
    observaciones_guardia = models.TextField(blank=True, default="")
    registrado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='visitas_creadas'
    )

    class Meta:
        ordering = ['-fecha_ingreso']
        verbose_name = 'Visita Externa'
        verbose_name_plural = 'Visitas Externas'

    def __str__(self):
        rut_str = f" [{self.rut_visitante}]" if self.rut_visitante else ""
        return f"{self.nombre_visitante}{rut_str} - {self.get_estado_display()}"

    @property
    def ha_egresado(self):
        return self.fecha_egreso is not None
