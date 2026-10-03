import logging

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from .forms import EquipoForm
from .models import Equipo
from .resiliencia import leer_equipos
from .servicios_equipos import ErrorAlGuardar, guardar_equipo_en_microservicio

logger = logging.getLogger(__name__)

# Valores que puede traer el boton del formulario (name="metodo").
METODO_PYTHON = "python"
METODO_JAVA = "java"
METODO_PHP = "php"
METODOS_DESDE_MICROSERVICIO = (METODO_JAVA, METODO_PHP)


def lista_equipos(request):
    # Patron vista -> modelo -> context -> template:
    # 1) la vista consulta los datos, 2) arma el context y 3) lo envia al template.
    #
    # La lectura es RESILIENTE: `leer_equipos` intenta el microservicio Node, si
    # falla el de Java, luego el de PHP y, si los tres no responden, vuelve al ORM
    # de Django. Los tres servicios leen la misma tabla `equipo` de Postgres, asi
    # que el contenido es el mismo y lo unico que cambia es quien lo sirvio.
    # La politica vive en `resiliencia.py` para poder probarla sin las vistas.
    equipos, origen = leer_equipos()
    context = {
        "equipos": equipos,
        # Para poder mostrar de donde vinieron los datos. "orm-sin-microservicios"
        # es el caso de caida total: conviene que sea visible en la pantalla, no
        # solo en el log, porque un usuario que ve datos viejos no puede saberlo.
        "origen_datos": origen,
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


def crear_equipo(request):
    # Patron vista -> modelo -> context -> template.
    # En GET se muestra el formulario vacio; en POST se valida, se guarda el
    # equipo y se redirige al listado para no reenviar el formulario al refrescar.
    #
    # Hay TRES botones de guardado y cada uno dice que hay que usar. No hace falta
    # JavaScript para distinguirlos: cada <button> lleva `name="metodo"` con su
    # propio `value`, asi que el navegador manda `metodo=python|java|php` en el POST
    # y la vista lee request.POST.get("metodo").
    #
    #   python -> guarda con el ORM de Django (comportamiento de siempre).
    #   java   -> POST al microservicio Java.
    #   php    -> POST al microservicio PHP.
    #
    # Los tres terminan escribiendo en la misma tabla `equipo` de Postgres, asi que
    # no hay que sincronizar nada: el equipo guardado por Java o PHP aparece en el
    # listado y en /api/equipos/ igual que si se hubiera guardado con Python.
    #
    # Si un microservicio esta caido NO se cae la pagina: se devuelve el formulario
    # con un error y el usuario puede reintentar con otro boton. Antes se valida el
    # formulario igual que con Python, para que ningun camino escriba datos que el
    # modelo no hubiera aceptado.
    error_servicio = None
    metodo = METODO_PYTHON

    if request.method == "POST":
        metodo = (request.POST.get("metodo") or METODO_PYTHON).strip().lower()
        form = EquipoForm(request.POST)
        if form.is_valid():
            if metodo in METODOS_DESDE_MICROSERVICIO:
                try:
                    guardar_equipo_en_microservicio(
                        metodo,
                        {
                            "nombre": form.cleaned_data["nombre"],
                            "tipo": form.cleaned_data["tipo"],
                            "disponible": form.cleaned_data["disponible"],
                        },
                    )
                except ErrorAlGuardar as exc:
                    logger.warning(
                        "No se pudo guardar el equipo por %s: %s", metodo, exc.detalle
                    )
                    error_servicio = exc.mensaje
                else:
                    return redirect("inventario:lista_equipos")
            else:
                # Python (o un valor desconocido): comportamiento actual, el ORM.
                form.save()
                return redirect("inventario:lista_equipos")
    else:
        form = EquipoForm()

    context = {
        "form": form,
        "accion": "Agregar equipo",
        "error_servicio": error_servicio,
    }
    return render(request, "inventario/crear_equipo.html", context)


def editar_equipo(request, equipo_id):
    # Patron vista -> modelo -> context -> template.
    # get_object_or_404 busca el equipo por pk o responde 404 si no existe.
    equipo = get_object_or_404(Equipo, pk=equipo_id)
    if request.method == "POST":
        form = EquipoForm(request.POST, instance=equipo)
        if form.is_valid():
            form.save()
            return redirect("inventario:lista_equipos")
    else:
        # instance=equipo precarga el formulario con los datos actuales.
        form = EquipoForm(instance=equipo)
    context = {
        "form": form,
        "equipo": equipo,
        "accion": "Editar equipo",
    }
    return render(request, "inventario/editar_equipo.html", context)


def eliminar_equipo(request, equipo_id):
    # Patron vista -> modelo -> context -> template.
    # GET muestra la pagina de confirmacion; POST borra y redirige al listado.
    equipo = get_object_or_404(Equipo, pk=equipo_id)
    if request.method == "POST":
        equipo.delete()
        return redirect("inventario:lista_equipos")
    context = {
        "equipo": equipo,
    }
    return render(request, "inventario/eliminar_equipo.html", context)


# ---------------------------------------------------------------------------
# API publica de solo lectura
# ---------------------------------------------------------------------------
#
# Estas vistas son el "contexto" que consume el chatbot: en vez de tocar el ORM
# desde tools.py, el modelo recibe los datos por HTTP contra estos endpoints. Asi
# el mismo dato se puede leer desde el navegador, con curl o desde otra maquina.


def _filtro_disponible(request):
    """Lee ?disponible=true|false. Devuelve None si no viene o no es valido."""
    valor = (request.GET.get("disponible") or "").strip().lower()
    if valor in ("true", "1", "si", "yes"):
        return True
    if valor in ("false", "0", "no"):
        return False
    return None


@require_GET
def api_equipos(request):
    """GET /api/equipos/ -> lista de equipos en JSON.

    Filtros opcionales: ?tipo=<clave> y ?disponible=true|false.
    Solo acepta GET: cualquier otro verbo responde 405.
    """
    consulta = Equipo.objects.all().order_by("id")

    tipo = (request.GET.get("tipo") or "").strip()
    if tipo:
        consulta = consulta.filter(tipo=tipo)

    disponible = _filtro_disponible(request)
    if disponible is not None:
        consulta = consulta.filter(disponible=disponible)

    equipos = [
        {
            "id": equipo.id,
            "nombre": equipo.nombre,
            # Se devuelve la etiqueta legible ("Laptop") y no la clave ("laptop")
            # porque el que consume esto es una IA: "Laptop" se responde directo
            # al usuario, mientras que la clave hay que traducirla.
            "tipo": equipo.get_tipo_display(),
            "disponible": equipo.disponible,
        }
        for equipo in consulta
    ]
    return JsonResponse({"equipos": equipos}, safe=False)
