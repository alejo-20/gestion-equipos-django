"""Escritura de equipos a traves de los microservicios Java y PHP.

Los botones "Guardar con Java" y "Guardar con PHP" del formulario de crear equipo
mandan el POST al microservicio que corresponda en vez de usar el ORM. Como los
microservicios escriben en la MISMA tabla `equipo` de Postgres que usa Django, el
equipo queda guardado y el ORM lo ve sin ninguna sincronizacion aparte.

Igual que en `resiliencia.py`, estas funciones nunca propagan una excepcion: si un
servicio esta caido, la vista lo reporta como un error de formulario y el usuario
puede volver a intentar con otro boton. Perder el dato guardado es molesto, pero
un error 500 en la pantalla es peor.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ErrorAlGuardar(Exception):
    """Fallo al guardar en un microservicio. El mensaje va al usuario.

    @param str mensaje de la vista.
    @param str detalle motivo tecnico, solo para el log.
    """

    def __init__(self, mensaje, detalle=""):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalle = detalle


def guardar_equipo_en_microservicio(nombre_servicio, datos):
    """Manda un equipo al microservicio indicado y devuelve el equipo creado.

    @param str nombre_servicio "java" o "php".
    @param dict datos con las claves `nombre`, `tipo` y `disponible`.
    @returns dict el equipo creado, con su `id`.
    @raises ErrorAlGuardar si el servicio no responde o devuelve un error.
    """
    if nombre_servicio == "java":
        url_base = settings.JAVA_SERVICE_URL
        etiqueta = "Java (Spring Boot)"
    elif nombre_servicio == "php":
        url_base = settings.PHP_SERVICE_URL
        etiqueta = "PHP"
    else:
        raise ValueError(
            f"'{nombre_servicio}' no es un microservicio valido. "
            "Use 'java' o 'php'."
        )

    url = f"{url_base.rstrip('/')}/equipos"

    try:
        respuesta = requests.post(url, json=datos, timeout=settings.TIMEOUT_MICROSERVICIOS)
    except requests.exceptions.Timeout:
        logger.warning("Timeout guardando el equipo en %s (%s).", etiqueta, url)
        raise ErrorAlGuardar(
            f"El microservicio {etiqueta} tardo demasiado en responder. "
            "Probalo de nuevo en un momento."
        )
    except requests.exceptions.ConnectionError as exc:
        logger.warning("No se pudo conectar con %s (%s): %s", etiqueta, url, exc)
        raise ErrorAlGuardar(
            f"No se pudo conectar con el microservicio {etiqueta}. "
            "Revisa que este corriendo."
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("Error de red guardando en %s (%s): %s", etiqueta, url, exc)
        raise ErrorAlGuardar(f"Error al guardar en {etiqueta}: {exc}")

    # 201 es lo que responden los dos servicios cuando el INSERT salio bien.
    if respuesta.status_code not in (200, 201):
        detalle = _extraer_error(respuesta)
        logger.warning(
            "%s respondio %s al guardar: %s", etiqueta, respuesta.status_code, detalle
        )
        raise ErrorAlGuardar(
            f"El microservicio {etiqueta} respondio con el estado "
            f"{respuesta.status_code}. Detalle: {detalle}"
        )

    try:
        cuerpo = respuesta.json()
    except ValueError as exc:
        logger.warning("%s devolvio una respuesta no valida: %s", etiqueta, exc)
        raise ErrorAlGuardar(
            f"El microservicio {etiqueta} devolvio una respuesta no valida."
        )

    logger.info(
        "Equipo guardado en %s (%s): %s", etiqueta, url, cuerpo.get("equipo")
    )
    return cuerpo.get("equipo", cuerpo)


def _extraer_error(respuesta):
    """Saca el mensaje de error del cuerpo JSON del microservicio.

    Los tres servicios usan `{"error": "..."}`. Si el cuerpo no es JSON (por
    ejemplo si hay un proxy delante), se devuelve un recorte del texto para que el
    log tenga algo util.
    """
    try:
        return respuesta.json().get("error", respuesta.text[:200])
    except ValueError:
        return respuesta.text[:200]
