from django import forms

from .models import Equipo


class EquipoForm(forms.ModelForm):
    # ModelForm del modelo Equipo: la vista solo se ocupa de validar con
    # form.is_valid() y guardar, el formulario hace el resto.
    class Meta:
        model = Equipo
        fields = ["nombre", "tipo", "disponible"]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej: Notebook Lenovo ThinkPad"}),
            "tipo": forms.Select(),
            "disponible": forms.CheckboxInput(),
        }
        labels = {
            "nombre": "Nombre del equipo",
            "tipo": "Tipo de equipo",
            "disponible": "Disponible",
        }
