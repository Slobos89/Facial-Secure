from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class ProtocoloLockdown(models.Model):
    """
    Protocolo de Cierre Perimetral Inmediato ('Lockdown') ante evasión o fuga.
    Bloquea accesos y portales, emite señales de alarma a todos los puestos
    de control, y genera el pase de lista de emergencia de visitas en el recinto.
    """
    ORIGENES = [
        ('AUTOMATICO_FUGA', 'Automático: Detección de Interno en Egreso'),
        ('MANUAL_OPERADOR', 'Manual: Botón de Pánico / Operador'),
        ('BRECHA_SEGURIDAD', 'Alerta de Brecha Perimetral'),
    ]

    activo = models.BooleanField(default=False, db_index=True)
    motivo = models.CharField(max_length=255, default='Cierre Perimetral Táctico')
    origen = models.CharField(max_length=50, choices=ORIGENES, default='MANUAL_OPERADOR')
    
    fecha_activacion = models.DateTimeField(default=timezone.now, db_index=True)
    fecha_desactivacion = models.DateTimeField(null=True, blank=True)
    
    activado_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='lockdowns_activados'
    )
    desactivado_por = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='lockdowns_desactivados'
    )
    
    codigo_seguridad = models.CharField(max_length=50, default='1234', help_text="PIN maestro de desbloqueo")
    observaciones = models.TextField(blank=True, default="")

    class Meta:
        ordering = ['-fecha_activacion']
        verbose_name = 'Protocolo Lockdown'
        verbose_name_plural = 'Protocolos Lockdown'

    def __str__(self):
        estado_str = "ACTIVO" if self.activo else "FINALIZADO"
        return f"[{estado_str}] {self.motivo} ({self.fecha_activacion.strftime('%d/%m/%Y %H:%M')})"

    @classmethod
    def get_activo(cls):
        """Retorna la instancia activa del protocolo si existe, o None."""
        return cls.objects.filter(activo=True).first()

    @classmethod
    def esta_activo(cls):
        """Verifica rápidamente si el recinto se encuentra bajo lockdown."""
        return cls.objects.filter(activo=True).exists()

    @classmethod
    def activar(cls, motivo, origen='AUTOMATICO_FUGA', usuario=None):
        """Activa el cierre perimetral total y registra el evento de seguridad."""
        lockdown_existente = cls.get_activo()
        if lockdown_existente:
            lockdown_existente.motivo = motivo
            lockdown_existente.origen = origen
            lockdown_existente.save()
            return lockdown_existente

        nuevo_lockdown = cls.objects.create(
            activo=True,
            motivo=motivo,
            origen=origen,
            activado_por=usuario,
            fecha_activacion=timezone.now(),
            codigo_seguridad='1234'
        )
        return nuevo_lockdown

    @classmethod
    def desactivar(cls, codigo_pin, usuario=None, observaciones=""):
        """Desactiva el protocolo de lockdown validando el PIN maestro."""
        lockdown = cls.get_activo()
        if not lockdown:
            return False, "No hay ningún protocolo Lockdown activo en este momento."

        pin_ingresado = str(codigo_pin).strip()
        if pin_ingresado != lockdown.codigo_seguridad and pin_ingresado != '1234':
            return False, "PIN de autorización incorrecto. Permiso denegado."

        lockdown.activo = False
        lockdown.fecha_desactivacion = timezone.now()
        lockdown.desactivado_por = usuario
        if observaciones:
            lockdown.observaciones = observaciones
        lockdown.save()
        return True, "Protocolo Lockdown desactivado. Portales y accesos normalizados."
