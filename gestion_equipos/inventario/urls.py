from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.lista_equipos, name="lista_equipos"),
    path("api/equipos/", views.api_equipos, name="api_equipos"),
    path("equipo/nuevo/", views.crear_equipo, name="crear_equipo"),
    path("equipo/<int:id>/", views.detalle_equipo, name="detalle_equipo"),
    path(
        "equipo/<int:equipo_id>/editar/",
        views.editar_equipo,
        name="editar_equipo",
    ),
    path(
        "equipo/<int:equipo_id>/eliminar/",
        views.eliminar_equipo,
        name="eliminar_equipo",
    ),
    path(
        "equipo/<int:id>/mantenimientos/",
        views.mantenimientos_equipo,
        name="mantenimientos_equipo",
    ),
]