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

    class Meta:
        # La tabla se llama `equipo` y no `inventario_equipo` porque es la tabla
        # COMPARTIDA con los tres microservicios (Java por JPA, Node por pg y PHP
        # por PDO): los cuatro tienen que tocar la misma fila fisicamente, asi que
        # se fija el nombre aca en vez de dejar el prefijo de app que Django elige
        # por defecto. Si se escribe `db_table = ...` como atributo de la clase en
        # lugar de adentro de Meta, Django lo IGNORA en silencio (no tira error) y
        # la tabla sigue llamandose inventario_equipo.
        db_table = 'equipo'

    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"