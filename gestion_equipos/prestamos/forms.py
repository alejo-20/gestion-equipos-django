from django import forms

from .models import Prestamo


class PrestamoForm(forms.ModelForm):
    # ModelForm del modelo Prestamo: la vista solo se ocupa de validar con
    # form.is_valid() y guardar, el formulario hace el resto.
    class Meta:
        model = Prestamo
        # fecha_prestamo no se incluye porque en el modelo tiene auto_now_add=True
        # (por eso es un campo no editable): la fecha y la hora las pone Django
        # sola al crear el prestamo y no se pueden enviar desde el formulario.
        fields = ["equipo", "nombre_persona", "fecha_devolucion", "devuelto"]
        widgets = {
            "equipo": forms.Select(),
            "nombre_persona": forms.TextInput(attrs={"placeholder": "Ej: Juan Perez"}),
            "fecha_devolucion": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "devuelto": forms.CheckboxInput(),
        }
        labels = {
            "equipo": "Equipo",
            "nombre_persona": "Nombre de la persona",
            "fecha_devolucion": "Fecha de devolucion",
            "devuelto": "Devuelto",
        }
