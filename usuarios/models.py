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

    nombre = models.CharField(max_length=100)

    apellido = models.CharField(max_length=100)

    rut = models.CharField(
        max_length=12,
        unique=True
    )

    tipo_persona = models.CharField(
        max_length=20,
        choices=TIPOS_PERSONA
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default='activo'
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

        PerfilUsuario.objects.create(

            user=instance,

            rol='GENDARME'
        )
    
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
        auto_now_add=True
    )

    camara = models.CharField(
        max_length=100
    )

    coincidencia = models.FloatField()

    resultado = models.CharField(
        max_length=20,
        choices=RESULTADOS
    )

    foto_validacion = models.ImageField(
        upload_to='validaciones/',
        blank=True,
        null=True
    )

    resuelto = models.BooleanField(
        default=False
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

    fecha_registro = models.DateTimeField(
        auto_now_add=True
    )

    activa = models.BooleanField(
        default=True
    )

    def __str__(self):

        return (
            f'Huella - '
            f'{self.persona.nombre}'
        )