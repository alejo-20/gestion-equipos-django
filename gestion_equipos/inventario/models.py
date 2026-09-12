from django.db import models


class Equipo(models.Model):
    TIPOS = [
        ('laptop', 'Laptop'),
        ('proyector', 'Proyector'),
        ('tablet', 'Tablet'),
        ('camara', 'Cámara'),
    ]

    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    disponible = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"