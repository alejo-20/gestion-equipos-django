from django.contrib import admin

from .models import Prestamo


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ("equipo", "nombre_persona", "fecha_prestamo", "fecha_devolucion", "devuelto")
    list_filter = ("devuelto",)
    search_fields = ("nombre_persona", "equipo__nombre")