from django.contrib import admin

from .models import Conversacion, Mensaje


@admin.register(Conversacion)
class ConversacionAdmin(admin.ModelAdmin):
    list_display = ("id", "session_key", "creada", "actualizada")
    search_fields = ("session_key",)
    readonly_fields = ("session_key", "creada", "actualizada")


@admin.register(Mensaje)
class MensajeAdmin(admin.ModelAdmin):
    list_display = ("id", "conversacion", "rol", "creado")
    list_filter = ("rol",)
    search_fields = ("texto",)
    # El campo pasos puede ser largo (JSON crudo de la API) y no aporta en la
    # vista de lista, asi que solo se muestra el texto.
    exclude = ("pasos",)
