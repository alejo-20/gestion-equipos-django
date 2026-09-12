from django.contrib import admin

from .models import Equipo


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "disponible")
    list_filter = ("tipo", "disponible")
    search_fields = ("nombre",)