from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventario.models import Equipo
from .models import Prestamo


def lista_prestamos_activos(request):
    prestamos = Prestamo.objects.filter(devuelto=False).select_related("equipo")
    return render(request, "prestamos/lista_prestamos.html", {"prestamos": prestamos})


def prestar_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    if request.method == "POST":
        nombre_persona = request.POST.get("nombre_persona", "").strip()
        if nombre_persona and equipo.disponible:
            Prestamo.objects.create(equipo=equipo, nombre_persona=nombre_persona)
            equipo.disponible = False
            equipo.save()
            return redirect("inventario:detalle_equipo", id=equipo.id)
    return render(request, "prestamos/prestar_equipo.html", {"equipo": equipo})


def devolver_prestamo(request, id):
    prestamo = get_object_or_404(Prestamo, id=id)
    if not prestamo.devuelto:
        prestamo.devuelto = True
        prestamo.fecha_devolucion = timezone.now()
        prestamo.save()
        equipo = prestamo.equipo
        equipo.disponible = True
        equipo.save()
    return redirect("prestamos:lista_prestamos_activos")