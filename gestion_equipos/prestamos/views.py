from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from inventario.models import Equipo
from .forms import PrestamoForm
from .models import Prestamo


# ---------------------------------------------------------------------------
# Sincronizacion del flag Equipo.disponible
# ---------------------------------------------------------------------------
#
# `Equipo.disponible` es un dato DERIVADO:depende de si el equipo tiene un
# prestamo con devuelto=False. Django no lo actualiza solo, asi que cada vista
# que crea, edita o borra un prestamo tiene que mantenerlo en sync a mano (lo
# mismo que ya hacia `devolver_prestamo`). Si se olvida en alguna, el chatbot
# contesta "esta disponible" por un equipo que alguien ya se llevo.
#
# La fuente de verdad sigue siendo la tabla Prestamo: estas funciones derived
# flags en un solo lugar para que las cuatro vistas queden consistentes entre si.


def _tiene_prestamo_activo(equipo, excluir=None):
    """¿El equipo tiene algun prestamo sin devolver?

    `excluir` sirve para no contar el prestamo que se esta editando o borrando:
    cuando se marca como devuelto, el equipo solo queda disponible si no tiene
    OTRO prestamo activo ademas de ese.
    """
    prestamos = Prestamo.objects.filter(equipo=equipo, devuelto=False)
    if excluir is not None:
        prestamos = prestamos.exclude(pk=excluir.pk)
    return prestamos.exists()


def _marcar_disponible(equipo, valor):
    """Deja el flag `disponible` del equipo en el valor pedido y lo guarda."""
    equipo.disponible = valor
    # update_fields porque solo se toca esa columna: un save() completo
    # reescribiria nombre y tipo con datos viejos si otro formulario los cambio
    # entre la lectura y este guardado.
    equipo.save(update_fields=["disponible"])


def _sincronizar_disponible_tras_editar(prestamo, equipo_anterior):
    """Recalcula `disponible` despues de editar un prestamo.

    Editar un prestamo puede cambiar las dos cosas que definen el estado de un
    equipo (que equipo es y si esta devuelto), asi que hay tres casos:

    1. Pasa a devuelto: el equipo vuelve a estar disponible, salvo que tenga
       otro prestamo activo aparte de este.
    2. Sigue activo (o vuelve de estar devuelto a activo): el equipo queda
       ocupado.
    3. Cambio de equipo: el nuevo queda ocupado y el anterior se libera, salvo
       que tambien tenga otro prestamo activo.
    """
    equipo = prestamo.equipo

    if prestamo.devuelto:
        # Este prestamo ya no ocupa el equipo.
        if not _tiene_prestamo_activo(equipo, excluir=prestamo):
            _marcar_disponible(equipo, True)
        # Si de paso cambio de equipo, el viejo tambien queda libre.
        _liberar_si_no_prestado(equipo_anterior, prestamo)
        return

    _marcar_disponible(equipo, False)
    if equipo_anterior.pk != equipo.pk:
        _liberar_si_no_prestado(equipo_anterior, prestamo)


def _liberar_si_no_prestado(equipo, prestamo):
    """Marca el equipo como disponible si no tiene ningun prestamo activo.

    `prestamo` es el que ya se devolvio o se va a borrar, asi que no cuenta como
    ocupacion: si solo estaba prestado por el, el equipo queda libre.
    """
    if equipo is None:
        return
    if not _tiene_prestamo_activo(equipo, excluir=prestamo):
        _marcar_disponible(equipo, True)


def lista_prestamos_activos(request):
    # Patron vista -> modelo -> context -> template.
    prestamos = Prestamo.objects.filter(devuelto=False).select_related("equipo")
    context = {
        "prestamos": prestamos,
    }
    return render(request, "prestamos/lista_prestamos.html", context)


def prestar_equipo(request, id):
    # Patron vista -> modelo -> context -> template.
    # get_object_or_404 busca el equipo por id o responde 404.
    equipo = get_object_or_404(Equipo, id=id)
    if request.method == "POST":
        nombre_persona = request.POST.get("nombre_persona", "").strip()
        if nombre_persona and equipo.disponible:
            Prestamo.objects.create(equipo=equipo, nombre_persona=nombre_persona)
            equipo.disponible = False
            equipo.save()
            return redirect("inventario:detalle_equipo", id=equipo.id)
    context = {
        "equipo": equipo,
    }
    return render(request, "prestamos/prestar_equipo.html", context)


def devolver_prestamo(request, id):
    # Patron vista -> modelo -> context -> template (aqui se redirige al finalizar).
    # get_object_or_404 busca el prestamo por id o responde 404.
    prestamo = get_object_or_404(Prestamo, id=id)
    if not prestamo.devuelto:
        prestamo.devuelto = True
        prestamo.fecha_devolucion = timezone.now()
        prestamo.save()
        equipo = prestamo.equipo
        equipo.disponible = True
        equipo.save()
    return redirect("prestamos:lista_prestamos_activos")


def crear_prestamo(request):
    # Patron vista -> modelo -> context -> template.
    # En GET se muestra el formulario vacio; en POST se valida, se guarda el
    # prestamo y se redirige al listado para no reenviar el formulario al refrescar.
    if request.method == "POST":
        form = PrestamoForm(request.POST)
        if form.is_valid():
            prestamo = form.save()
            # El prestamo ya existe en la base, asi que ahora el equipo se marca
            # como ocupado. Antes solo lo hacia `prestar_equipo` y por eso crear
            # un prestamo desde este formulario dejaba el equipo "disponible".
            # El formulario tambien expone `devuelto`: si el prestamo nace ya
            # devuelto el equipo sigue libre y no hay que tocar el flag.
            if not prestamo.devuelto:
                _marcar_disponible(prestamo.equipo, False)
            return redirect("prestamos:lista_prestamos_activos")
    else:
        form = PrestamoForm()
    context = {
        "form": form,
        "accion": "Agregar prestamo",
    }
    return render(request, "prestamos/crear_prestamo.html", context)


def editar_prestamo(request, prestamo_id):
    # Patron vista -> modelo -> context -> template.
    # get_object_or_404 busca el prestamo por pk o responde 404 si no existe.
    prestamo = get_object_or_404(Prestamo.objects.select_related("equipo"), pk=prestamo_id)
    # El equipo anterior se captura ANTES de construir el formulario, y no dentro
    # del if form.is_valid(): al validar, Django ya le escribe a `prestamo` los
    # valores nuevos (form._post_clean) y `prestamo.equipo` pasa a ser el equipo
    # nuevo. Guardandolo aca queda el de verdad, que es el que hay que liberar.
    equipo_anterior = prestamo.equipo
    if request.method == "POST":
        form = PrestamoForm(request.POST, instance=prestamo)
        if form.is_valid():
            prestamo = form.save()
            _sincronizar_disponible_tras_editar(prestamo, equipo_anterior)
            return redirect("prestamos:lista_prestamos_activos")
    else:
        # instance=prestamo precarga el formulario con los datos actuales.
        form = PrestamoForm(instance=prestamo)
    context = {
        "form": form,
        "prestamo": prestamo,
        "accion": "Editar prestamo",
    }
    return render(request, "prestamos/editar_prestamo.html", context)


def eliminar_prestamo(request, prestamo_id):
    # Patron vista -> modelo -> context -> template.
    # GET muestra la pagina de confirmacion; POST borra y redirige al listado.
    prestamo = get_object_or_404(Prestamo.objects.select_related("equipo"), pk=prestamo_id)
    if request.method == "POST":
        # Borrar un prestamo activo libera el equipo. Si no se hiciera, el
        # equipo quedaria marcado como no disponible para siempre aunque ya no
        # haya nadie con el. El chequeo corre antes del delete porque despues
        # este prestamo ya no se podria excluir de la cuenta de los activos.
        if not prestamo.devuelto:
            _liberar_si_no_prestado(prestamo.equipo, prestamo)
        prestamo.delete()
        return redirect("prestamos:lista_prestamos_activos")
    context = {
        "prestamo": prestamo,
    }
    return render(request, "prestamos/eliminar_prestamo.html", context)


# ---------------------------------------------------------------------------
# API publica de solo lectura
# ---------------------------------------------------------------------------
#
# Complementa a inventario.api_equipos: es el otro endpoint que consume el
# chatbot por HTTP para armar su contexto sin leer el ORM.


@require_GET
def api_prestamos(request):
    """GET /api/prestamos/ -> lista de prestamos en JSON.

    Filtros opcionales: ?estado=activo|devuelto y ?persona=<texto>.
    Sin ?estado se devuelven todos. Solo acepta GET: otro verbo responde 405.
    """
    consulta = Prestamo.objects.select_related("equipo").order_by("id")

    estado = (request.GET.get("estado") or "").strip().lower()
    if estado == "activo":
        consulta = consulta.filter(devuelto=False)
    elif estado == "devuelto":
        consulta = consulta.filter(devuelto=True)

    persona = (request.GET.get("persona") or "").strip()
    if persona:
        consulta = consulta.filter(nombre_persona__icontains=persona)

    # JsonResponse serializa los datetimes con DjangoJSONEncoder, asi que las
    # fechas salen en ISO 8601 sin convertirlas a mano.
    prestamos = [
        {
            "id": prestamo.id,
            "equipo_id": prestamo.equipo_id,
            "equipo": prestamo.equipo.nombre,
            "nombre_persona": prestamo.nombre_persona,
            "fecha_prestamo": prestamo.fecha_prestamo,
            "fecha_devolucion": prestamo.fecha_devolucion,
            "devuelto": prestamo.devuelto,
        }
        for prestamo in consulta
    ]
    return JsonResponse({"prestamos": prestamos}, safe=False)
