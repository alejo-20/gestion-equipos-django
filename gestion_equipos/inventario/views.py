import requests
from django.conf import settings
from django.shortcuts import get_object_or_404, render

from .models import Equipo


def lista_equipos(request):
    # Patron vista -> modelo -> context -> template:
    # 1) la vista consulta el modelo, 2) arma el context y 3) lo envia al template.
    equipos = Equipo.objects.all()
    context = {
        "equipos": equipos,
    }
    return render(request, "inventario/lista_equipos.html", context)


def detalle_equipo(request, id):
    # Patron vista -> modelo -> context -> template.
    # get_object_or_404 evita Model.objects.get() y responde 404 si no existe.
    equipo = get_object_or_404(Equipo, id=id)
    context = {
        "equipo": equipo,
    }
    return render(request, "inventario/detalle_equipo.html", context)


def mantenimientos_equipo(request, id):
    # Patron vista -> modelo -> context -> template.
    # La vista obtiene el equipo, consulta el microservicio de mantenimientos
    # y arma el context; el template solo se encarga de presentar los datos.
    equipo = get_object_or_404(Equipo, id=id)

    mantenimientos = []
    total_gastado = 0
    error = None

    url = f"{settings.MICROSERVICIO_URL}/mantenimientos/{equipo.id}"
    try:
        # timeout=60 porque el free tier de Render tarda en despertar.
        respuesta = requests.get(url, timeout=60)
        if respuesta.status_code == 200:
            mantenimientos = respuesta.json()
            total_gastado = sum(float(m.get("costo") or 0) for m in mantenimientos)
        else:
            error = (
                "El microservicio de mantenimientos respondio con el estado "
                f"{respuesta.status_code}."
            )
    except requests.exceptions.Timeout:
        error = "El microservicio de mantenimientos tardo demasiado en responder (timeout de 60s)."
    except requests.exceptions.ConnectionError:
        error = "No se pudo conectar con el microservicio de mantenimientos."
    except requests.exceptions.RequestException as exc:
        error = f"Error al consultar el microservicio de mantenimientos: {exc}"
    except ValueError:
        error = "El microservicio de mantenimientos devolvio una respuesta no valida."

    context = {
        "equipo": equipo,
        "mantenimientos": mantenimientos,
        "total_gastado": total_gastado,
        "error": error,
    }
    return render(request, "inventario/mantenimientos_equipo.html", context)
