from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.lista_equipos, name="lista_equipos"),
    path("equipo/<int:id>/", views.detalle_equipo, name="detalle_equipo"),
]