"""Herramientas del chatbot: declaracion para Gemini + implementacion en Django.

Este modulo es la unica fuente de verdad sobre QUE puede consultar el chatbot.
El modelo no escribe nada en la base de datos: todas las herramientas son de
solo lectura.

Las declaraciones se escriben en JSON Schema plano porque el modelo decide que
tool usar leyendo `description`. Por eso el texto de cada descripcion importa
tanto como el codigo que la ejecuta: ahi se explica cuando usarla y cuando NO.

Dos formas distintas de traer el mismo dato, y la diferencia es el punto de la
actividad: el modelo no tiene acceso a la base, recibe un contexto que el
proyecto le expone. `consultar_equipos` y `consultar_prestamos` lo hacen por
HTTP contra los endpoints publicos /api/ (los mismos que se pueden abrir en el
navegador o con curl), mientras que `consultar_equipo` y `consultar_mantenimientos`
siguen leyendo el ORM y el microservicio respectivamente.

Para responder "quien tiene este equipo", la fuente de verdad es la tabla
Prestamo (devuelto=False) y no el campo `Equipo.disponible`: ese flag es un
valor derivado que se puede desincronizar, y cuando se desincroniza el chatbot
da informacion desactualizada. Por eso `consultar_equipo` deriva el estado del
prestamo activo, igual que `consultar_prestamos` lo trae de /api/prestamos/.
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone

from inventario.models import Equipo
from prestamos.models import Prestamo

logger = logging.getLogger(__name__)

# Timeout para el microservicio de mantenimientos. Es mucho mas corto que el
# timeout=60 de inventario/views.py porque aqui el usuario esta esperando una
# respuesta de chat: 60s de silencio en un chat es indistinguible de un cuelgue.
TIMEOUT_MANTENIMIENTOS = 15

# Timeout para la API publica del propio proyecto. Es la mas rapida de las dos
# (consulta una base local), asi que un timeout corto falla rapido y el chat
# puede explicarle al usuario que no pudo consultar en vez de quedarse mudo.
TIMEOUT_API = 5


# ---------------------------------------------------------------------------
# Declaraciones
# ---------------------------------------------------------------------------
#
# OJO: la Interactions API usa el formato plano {"type": "function", "name",
# "description", "parameters"}. No es el formato anidado de la API legacy
# generateContent ({"type": "function", "function": {...}}), que devuelve
# 400 "Missing name in function tool".

HERRAMIENTAS = [
    {
        "type": "function",
        "name": "consultar_equipos",
        "description": (
            "Lista el catalogo de equipos. Usala para preguntas generales sobre "
            "que equipos hay, cuantos son de cierto tipo o cuantos estan "
            "disponibles. Si la pregunta es sobre UN equipo concreto, usa "
            "consultar_equipo. No la uses para preguntar por mantenimientos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": [clave for clave, _ in Equipo.TIPOS],
                    "description": "Filtro opcional por tipo de equipo.",
                },
                "disponible": {
                    "type": "boolean",
                    "description": "Filtro opcional por disponibilidad.",
                },
            },
        },
    },
    {
        "type": "function",
        "name": "consultar_equipo",
        "description": (
            "Detalle de un equipo segun su id, incluyendo a quien se lo presto y "
            "desde cuando, si esta prestado. Usala siempre que la pregunta "
            "mencione un equipo concreto. No requiere el historial de "
            "mantenimiento."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "equipo_id": {
                    "type": "integer",
                    "description": "Id numerico del equipo.",
                }
            },
            "required": ["equipo_id"],
        },
    },
    {
        "type": "function",
        "name": "consultar_prestamos",
        "description": (
            "Lista los prestamos con el equipo, la persona, la fecha de entrega "
            "y la de devolucion. Usala para preguntas como 'quien tiene el "
            "proyector', 'que equipos estan prestados' o 'que presto Juan'. "
            "No la uses para consultar mantenimientos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "estado": {
                    "type": "string",
                    "enum": ["activo", "devuelto"],
                    "description": (
                        "Filtro opcional. Si se omite, solo prestamos activos."
                    ),
                },
                "persona": {
                    "type": "string",
                    "description": (
                        "Filtro opcional por nombre de la persona, busqueda parcial."
                    ),
                },
            },
        },
    },
    {
        "type": "function",
        "name": "consultar_mantenimientos",
        "description": (
            "Historial de mantenimientos de un equipo y el costo total gastado. "
            "Usa la SOLO si la pregunta es sobre mantenimiento, reparacion, "
            "reemplazo o costo de servicio. Este dato vive en un servicio "
            "externo y puede tardar en responder, asi que no lo consultes si la "
            "pregunta se puede responder con el estado del equipo o los "
            "prestamos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "equipo_id": {
                    "type": "integer",
                    "description": "Id numerico del equipo.",
                }
            },
            "required": ["equipo_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Serializacion
# ---------------------------------------------------------------------------


def _iso(valor):
    if valor is None:
        return None
    if timezone.is_naive(valor):
        valor = timezone.make_aware(valor, timezone.get_default_timezone())
    return valor.isoformat()


def _equipo_a_dict(equipo, prestamo_activo=None):
    """Arma el dict de un equipo a partir de su prestamo activo.

    El prestamo se recibe ya resuelto (lo busca la tool que llama) y no se
    consulta aca para que quede obvio de donde sale el dato.
    """
    return {
        "id": equipo.id,
        "nombre": equipo.nombre,
        "tipo": equipo.get_tipo_display(),
        # `disponible` se deriva del prestamo activo y no del campo homonimo del
        # modelo, por la misma razon que `prestado_a`: el flag se desincroniza
        # (si se borra un prestamo, si se edita uno devuelto...) y cuando pasa
        # el chatbot afirma que un equipo prestado esta libre.
        "disponible": prestamo_activo is None,
        "prestado_a": prestamo_activo.nombre_persona if prestamo_activo else None,
        "fecha_prestamo": _iso(prestamo_activo.fecha_prestamo) if prestamo_activo else None,
    }


# ---------------------------------------------------------------------------
# Cliente de la API publica
# ---------------------------------------------------------------------------


def _get_api(ruta, params, etiqueta):
    """Llama por HTTP a un endpoint publico de este proyecto y devuelve su JSON.

    Devuelve (datos, None) si todo sale bien, o (None, mensaje_de_error) si
    falla. Nunca propaga excepciones: un error de red es un resultado mas de la
    tool, no una excepcion que tumbe el turno, porque el modelo tiene que poder
    explicarle al usuario que no pudo consultar.
    """
    url = f"{settings.API_BASE_URL}{ruta}"
    try:
        respuesta = requests.get(url, params=params, timeout=TIMEOUT_API)
        if respuesta.status_code != 200:
            return None, (
                f"La API de {etiqueta} respondio con el estado "
                f"{respuesta.status_code}."
            )
        return respuesta.json(), None
    except requests.exceptions.Timeout:
        return None, (
            f"La API de {etiqueta} tardo demasiado en responder. Indica al "
            "usuario que no se pudo consultar en este momento."
        )
    except requests.exceptions.ConnectionError:
        return None, (
            f"No se pudo conectar con la API de {etiqueta}. Recuerda al usuario "
            "que el servidor tiene que estar corriendo."
        )
    except requests.exceptions.RequestException as exc:
        return None, f"Error al consultar la API de {etiqueta}: {exc}"
    except ValueError:
        return None, f"La API de {etiqueta} devolvio una respuesta no valida."


# ---------------------------------------------------------------------------
# Implementaciones (solo lectura)
# ---------------------------------------------------------------------------


def consultar_equipos(tipo=None, disponible=None):
    """Catalogo de equipos leido del endpoint publico /api/equipos/.

    Filtra por tipo y por disponibilidad, igual que antes, pero los datos ya no
    salen del ORM: viajan por HTTP como lo veria cualquier cliente de la API.
    """
    params = {}

    if tipo is not None:
        validos = {clave for clave, _ in Equipo.TIPOS}
        if tipo not in validos:
            return {
                "error": (
                    f"El tipo '{tipo}' no es valido. Tipos validos: "
                    f"{', '.join(sorted(validos))}."
                )
            }
        params["tipo"] = tipo

    if disponible is not None:
        params["disponible"] = "true" if disponible else "false"

    datos, error = _get_api("/api/equipos/", params, "equipos")
    if error:
        return {"error": error}

    equipos = datos.get("equipos", [])
    return {
        "cantidad": len(equipos),
        "equipos": equipos,
    }


def consultar_equipo(equipo_id):
    """Detalle de un equipo por id.

    "A quien esta prestado" se determina buscando el prestamo ACTIVO
    (devuelto=False) de ese equipo en la tabla Prestamo, no leyendo
    `Equipo.disponible`. Ese flag es un valor derivado que se puede
    desincronizar, y cuando se desincroniza el chatbot miente: contestaba
    "nadie lo tiene, esta disponible" para equipos que ya tenian un prestamo
    activo. Leyendo la tabla Prestamo el estado es correcto siempre, se haya
    sincronizado el flag o no.
    """
    equipo = Equipo.objects.filter(id=equipo_id).first()
    if equipo is None:
        return {"error": f"No existe un equipo con id {equipo_id}."}

    prestamo_activo = (
        Prestamo.objects.filter(equipo_id=equipo_id, devuelto=False)
        .select_related("equipo")
        # Si por error de carga hay mas de un prestamo activo del mismo equipo,
        # gana el mas reciente: es el que el usuario quiere saber quien lo tiene.
        .order_by("-fecha_prestamo")
        .first()
    )
    return {"equipo": _equipo_a_dict(equipo, prestamo_activo)}


def consultar_prestamos(estado="activo", persona=None):
    """Prestamos leidos del endpoint publico /api/prestamos/.

    El endpoint llama `nombre_persona` al nombre de quien recibe el equipo, pero
    la tool se lo devuelve al modelo como `persona` (y agrega `equipo_id`): es
    el mismo contexto de siempre, asi el `system_instruction` y las respuestas
    del modelo no cambian por haber movido la lectura a la API.
    """
    if estado not in ("activo", "devuelto"):
        estado = "activo"

    params = {"estado": estado}
    if persona:
        params["persona"] = str(persona).strip()

    datos, error = _get_api("/api/prestamos/", params, "prestamos")
    if error:
        return {"error": error}

    prestamos = [
        {
            "id": prestamo.get("id"),
            "equipo_id": prestamo.get("equipo_id"),
            "equipo": prestamo.get("equipo"),
            "persona": prestamo.get("nombre_persona"),
            "fecha_prestamo": prestamo.get("fecha_prestamo"),
            "fecha_devolucion": prestamo.get("fecha_devolucion"),
            "devuelto": prestamo.get("devuelto"),
        }
        for prestamo in datos.get("prestamos", [])
    ]
    return {
        "estado": estado,
        "cantidad": len(prestamos),
        "prestamos": prestamos,
    }


def consultar_mantenimientos(equipo_id):
    """Historial de mantenimientos de un equipo, vía microservicio FastAPI."""
    equipo = Equipo.objects.filter(id=equipo_id).first()
    if equipo is None:
        return {"error": f"No existe un equipo con id {equipo_id}."}

    url = f"{settings.MICROSERVICIO_URL}/mantenimientos/{equipo_id}"
    try:
        respuesta = requests.get(url, timeout=TIMEOUT_MANTENIMIENTOS)
        if respuesta.status_code != 200:
            return {
                "error": (
                    "El microservicio de mantenimientos respondio con el estado "
                    f"{respuesta.status_code}."
                )
            }
        mantenimientos = respuesta.json()
    except requests.exceptions.Timeout:
        return {
            "error": (
                "El microservicio de mantenimientos tardo demasiado en responder. "
                "Indica al usuario que no se pudo consultar el historial en este "
                "momento."
            )
        }
    except requests.exceptions.ConnectionError:
        return {
            "error": (
                "No se pudo conectar con el microservicio de mantenimientos. "
                "Recuerdale al usuario que debe estar corriendo en el puerto 8001."
            )
        }
    except requests.exceptions.RequestException as exc:
        return {"error": f"Error al consultar el microservicio: {exc}"}
    except ValueError:
        return {
            "error": "El microservicio de mantenimientos devolvio una respuesta no valida."
        }

    # El total se calcula aqui, nunca se le pide al modelo que lo sume.
    total_gastado = sum(float(m.get("costo") or 0) for m in mantenimientos)

    return {
        "equipo": {"id": equipo.id, "nombre": equipo.nombre},
        "cantidad": len(mantenimientos),
        "mantenimientos": mantenimientos,
        "total_gastado": round(total_gastado, 2),
    }


# ---------------------------------------------------------------------------
# Despacho
# ---------------------------------------------------------------------------

FUNCIONES = {
    "consultar_equipos": consultar_equipos,
    "consultar_equipo": consultar_equipo,
    "consultar_prestamos": consultar_prestamos,
    "consultar_mantenimientos": consultar_mantenimientos,
}


def ejecutar(nombre, argumentos):
    """Ejecuta una tool solicitada por el modelo.

    Nunca propaga excepciones: un error aqui se devuelve como resultado para que
    el modelo lo explique, en vez de tumbar el turno completo.
    """
    funcion = FUNCIONES.get(nombre)
    if funcion is None:
        return {"error": f"La herramienta '{nombre}' no existe."}

    argumentos = argumentos or {}
    if not isinstance(argumentos, dict):
        return {"error": f"Los argumentos de '{nombre}' no son un objeto."}

    try:
        return funcion(**argumentos)
    except TypeError as exc:
        # El modelo invento un argumento que la funcion no acepta.
        return {
            "error": (
                f"Argumentos invalidos para '{nombre}'. "
                f"Esperados: {', '.join(FUNCIONES[nombre].__code__.co_varnames[: FUNCIONES[nombre].__code__.co_argcount])}. "
                f"Detalle: {exc}"
            )
        }
    except Exception as exc:  # noqa: BLE001 - frontera con el modelo, no debe tumbar el turno
        logger.exception("Fallo la herramienta %s con argumentos %s", nombre, argumentos)
        return {"error": f"Ocurrio un error ejecutando '{nombre}': {exc}"}
