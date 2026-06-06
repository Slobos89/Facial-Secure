from django import forms
from .models import Persona


class PersonaForm(forms.ModelForm):

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