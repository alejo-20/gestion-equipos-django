from django.urls import path

from . import views

app_name = "prestamos"

urlpatterns = [
    path("prestamos/", views.lista_prestamos_activos, name="lista_prestamos_activos"),
    path("api/prestamos/", views.api_prestamos, name="api_prestamos"),
    path("prestamos/nuevo/", views.crear_prestamo, name="crear_prestamo"),
    path("equipo/<int:id>/prestar/", views.prestar_equipo, name="prestar_equipo"),
    path("prestamo/<int:id>/devolver/", views.devolver_prestamo, name="devolver_prestamo"),
    path(
        "prestamo/<int:prestamo_id>/editar/",
        views.editar_prestamo,
        name="editar_prestamo",
    ),
    path(
        "prestamo/<int:prestamo_id>/eliminar/",
        views.eliminar_prestamo,
        name="eliminar_prestamo",
    ),
]