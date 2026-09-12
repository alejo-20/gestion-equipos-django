from django.urls import path

from . import views

app_name = "prestamos"

urlpatterns = [
    path("prestamos/", views.lista_prestamos_activos, name="lista_prestamos_activos"),
    path("equipo/<int:id>/prestar/", views.prestar_equipo, name="prestar_equipo"),
    path("prestamo/<int:id>/devolver/", views.devolver_prestamo, name="devolver_prestamo"),
]