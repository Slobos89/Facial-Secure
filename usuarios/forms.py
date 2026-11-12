from django import forms
from .models import Persona


class PersonaForm(forms.ModelForm):

    TIPO_ENROLAMIENTO_CHOICES = [
        ('interno', 'Interno'),
        ('externo', 'Externo / Visita'),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_persona'].choices = self.TIPO_ENROLAMIENTO_CHOICES

    def clean_tipo_persona(self):
        tipo = self.cleaned_data.get('tipo_persona')
        if tipo == 'gendarme':
            raise forms.ValidationError(
                'Los funcionarios gendarmes deben registrarse desde el módulo "Registrar Gendarme".'
            )
        return tipo

    class Meta:

        model = Persona

        widgets = {
            'rut': forms.TextInput(
                attrs={
                    'id': 'rut',
                    'maxlength': '12',
                    'placeholder': '12.345.678-9'
                }
            )
        }

        fields = [
            'nombre',
            'apellido',
            'rut',
            'tipo_persona',
            'estado',
            'foto',
        ]