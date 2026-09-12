from django.db import models
from django.utils import timezone

from inventario.models import Equipo


class Prestamo(models.Model):
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="prestamos")
    nombre_persona = models.CharField(max_length=100)
    fecha_prestamo = models.DateTimeField(auto_now_add=True)
    fecha_devolucion = models.DateTimeField(null=True, blank=True)
    devuelto = models.BooleanField(default=False)

    def __str__(self):
        estado = "Devuelto" if self.devuelto else "Activo"
        return f"{self.equipo.nombre} -> {self.nombre_persona} ({estado})"