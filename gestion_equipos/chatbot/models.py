from django.db import models


class Conversacion(models.Model):
    """Una sesion de chat. Se identifica por la clave de la sesion de Django."""

    session_key = models.CharField(max_length=64, db_index=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conversacion"
        verbose_name_plural = "Conversaciones"
        ordering = ["-actualizada"]

    def __str__(self):
        return f"Conversacion #{self.pk} ({self.session_key[:8]})"


class Mensaje(models.Model):
    """Un turno de la conversacion.

    `pasos` guarda los steps crudos que devolvio Gemini (model_output,
    function_call, function_result, thought) tal cual los recibio la API.

    Este campo NO es opcional: cuando la conversacion se reproduce sin estado
    (store=False) hay que reenviar esos steps literalmente porque contienen las
    "thought signatures" que la API exige para continuar el hilo. Si solo se
    guardara el texto, el segundo turno con function calling falla.
    """

    ROLES = [
        ("user", "Usuario"),
        ("bot", "Asistente"),
    ]

    conversacion = models.ForeignKey(
        Conversacion,
        on_delete=models.CASCADE,
        related_name="mensajes",
    )
    rol = models.CharField(max_length=10, choices=ROLES)
    texto = models.TextField(blank=True)
    pasos = models.JSONField(default=list, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mensaje"
        verbose_name_plural = "Mensajes"
        ordering = ["id"]

    def __str__(self):
        return f"[{self.rol}] {self.texto[:60]}"
