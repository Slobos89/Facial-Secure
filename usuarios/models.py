from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# Create your models here.
class Persona(models.Model):

    TIPOS_PERSONA = [
        ('interno', 'Interno'),
        ('gendarme', 'Gendarme'),
        ('externo', 'Externo'),
    ]

    ESTADOS = [
        ('activo', 'Activo'),
        ('bloqueado', 'Bloqueado'),
        ('suspendido', 'Suspendido'),
    ]

    ENROLAMIENTOS = [
        ('pendiente', 'Pendiente'),
        ('parcial', 'Parcial'),
        ('completo', 'Completo'),
    ]

    nombre = models.CharField(max_length=100)

    apellido = models.CharField(max_length=100)

    rut = models.CharField(
        max_length=50,
        unique=True
    )

    tipo_persona = models.CharField(
        max_length=20,
        choices=TIPOS_PERSONA,
        db_index=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='activo',
        db_index=True
    )

    estado_enrolamiento = models.CharField(
        max_length=20,
        choices=ENROLAMIENTOS,
        default='pendiente'
    )

    biometria_facial = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica si el modelo de IA ya fue entrenado con este rostro"
    )

    embedding_facial = models.JSONField(
        null=True,
        blank=True,
        help_text="Vector matemático de características faciales Deep Learning (128-d)"
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    foto = models.ImageField(
        upload_to='rostros/',
        blank=True,
        null=True
    )

    foto_rostro = models.ImageField(
        upload_to='rostros_recortados/',
        blank=True,
        null=True
    )

    def __str__(self):
        return f"{self.nombre} {self.apellido}"
    
class PerfilUsuario(models.Model):

    ROLES = [

        ('ADMIN','Administrador'),

        ('GENDARME','Gendarme'),

    ]


    user = models.OneToOneField(

        User,

        on_delete=models.CASCADE

    )

    persona = models.OneToOneField(

        Persona,

        on_delete=models.CASCADE,

        null=True,

        blank=True
    )


    rol = models.CharField(

        max_length=20,

        choices=ROLES

    )


    def __str__(self):

        return f'{self.user.username} - {self.rol}'
    
@receiver(post_save, sender=User)
def crear_perfil_usuario(

    sender,

    instance,

    created,

    **kwargs

):

    if created:
        PerfilUsuario.objects.get_or_create(user=instance, defaults={'rol': 'GENDARME'})

    
class Acceso(models.Model):

    RESULTADOS = [
        ('PERMITIDO', 'Permitido'),
        ('DENEGADO', 'Denegado'),
        ('REVISION', 'Revisión'),
    ]

    persona = models.ForeignKey(
        Persona,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    nombre_detectado = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    fecha_hora = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    camara = models.CharField(
        max_length=100
    )

    coincidencia = models.FloatField()

    resultado = models.CharField(
        max_length=20,
        choices=RESULTADOS,
        db_index=True
    )

    foto_validacion = models.ImageField(
        upload_to='validaciones/',
        blank=True,
        null=True
    )

    resuelto = models.BooleanField(
        default=False,
        db_index=True
    )

    motivo_resolucion = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    resuelto_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='alertas_resueltas'
    )

    fecha_resolucion = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):

        if self.persona:
            return f'{self.persona} - {self.resultado}'

        return f'Desconocido - {self.resultado}'
    
class RostroCapturado(models.Model):

    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name='rostros'
    )

    imagen = models.ImageField(
        upload_to='rostros_dataset/'
    )

    fecha = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):

        return f'{self.persona} - Rostro'
    
class HuellaDactilar(models.Model):

    persona = models.OneToOneField(

        Persona,

        on_delete=models.CASCADE,

        related_name='huella'

    )

    template = models.TextField()

    calidad = models.IntegerField(
        default=0,
        blank=True,
        null=True
    )

    formato = models.CharField(
        max_length=20,
        default='ANSI378'
    )

    imagen_muestra = models.TextField(
        blank=True,
        null=True
    )

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    activa = models.BooleanField(
        default=True
    )

    def __str__(self):
        return f"Huella de {self.persona}"


class ConfiguracionCamara(models.Model):
    TIPOS = [
        ('ip_yoosee', 'Cámara IP (ONVIF / RTSP)'),
        ('webcam', 'Webcam Local (USB / Integrada)'),
    ]

    nombre = models.CharField(max_length=120, default="Cámara Principal (IP Yoosee)")
    tipo = models.CharField(max_length=20, choices=TIPOS, default='ip_yoosee')
    ip = models.CharField(max_length=50, default='192.168.100.34', blank=True, null=True)
    puerto_onvif = models.IntegerField(default=5000)
    puerto_rtsp = models.IntegerField(default=554)
    usuario = models.CharField(max_length=50, default='admin', blank=True)
    password = models.CharField(max_length=100, default='admin12345', blank=True)
    stream = models.CharField(max_length=50, default='onvif2', blank=True)
    webcam_index = models.IntegerField(default=0)
    activa = models.BooleanField(default=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración de Cámara"
        verbose_name_plural = "Configuraciones de Cámara"

    def __str__(self):
        if self.tipo == 'ip_yoosee':
            return f"{self.nombre} [{self.ip}]"
        return f"{self.nombre} [Dispositivo #{self.webcam_index}]"

    @classmethod
    def get_activa(cls, cam_id=None):
        if cam_id:
            try:
                cam = cls.objects.filter(id=cam_id).first()
                if cam:
                    return cam
            except Exception:
                pass
        cam = cls.objects.filter(activa=True).order_by('-fecha_actualizacion').first()
        if not cam:
            cam = cls.objects.create(
                nombre="Webcam Local #0",
                tipo="webcam",
                webcam_index=0,
                activa=True
            )
        return cam