from django.shortcuts import get_object_or_404, render

from .models import Equipo


def lista_equipos(request):
    equipos = Equipo.objects.all()
    return render(request, "inventario/lista_equipos.html", {"equipos": equipos})


def detalle_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    return render(request, "inventario/detalle_equipo.html", {"equipo": equipo})