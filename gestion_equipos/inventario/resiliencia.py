"""Lectura resiliente del inventario: Node -> Java -> PHP -> ORM.

Este modulo es el corazon del punto 4 del requerimiento y esta SEPARADO de
`views.py` a proposito: la vista solo pide "dame los equipos" y este modulo
decide de donde salen. Asi la politica de reintentos se puede probar sin levantar
los tres servicios.

Por que un orden y no "el primero que responda": cada microservicio habla con la
MISMA tabla `equipo` de Postgres, asi que los tres devuelven exactamente lo
mismo. El orden es por costo de respuesta, no por contenido:

    1. Node (8082)   Express, sin contenedor de inyeccion ni JVM: el mas liviano.
    2. Java  (8081)  Spring Boot: tarda mas en arrancar, pero una vez arriba es
                     estable y tiene pool de conexiones y transacciones.
    3. PHP   (8083)  Corre con el servidor embebido, que es single-threaded: es el
                     que mas se resiente si llegan varias peticiones a la vez, por
                     eso va ultimo.
    4. ORM de Django Si los tres fallan, el usuario igual ve la lista. Nunca se
                     devuelve una pagina vacia por un problema de infraestructura.

El timeout por intento es corto (3s, `settings.TIMEOUT_MICROSERVICIOS`) porque el
usuario esta esperando la pagina. En el peor caso se chega a esperar 9s (3 x 3),
que es preferible a una request colgada: el navegador agota antes.

Que se considera un fallo y hace avanzar al siguiente:
    - timeout, conexion rechazada o cualquier error de red;
    - estado >= 500 (el servicio esta caido o la base no responde);
    - cuerpo que no es JSON valido, o que no trae la lista de equipos.

Un 4xx NO hace avanzar: si el servicio responde 404 o 400 es que contesto, y
saltear al siguiente solo esconderia el problema real.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def normalizar_url_servicio(valor):
    if not valor:
        return valor
    if valor.startswith("http://") or valor.startswith("https://"):
        return valor
    return f"https://{valor}"


# Orden de la cadena de lectura. Es una lista de tuplas (nombre, atributo de
# settings) para que agregar un cuarto servicio sea agregar una linea y no tocar
# el codigo que la recorre.
CADENA_DE_LECTURA = (
    ("node", "NODE_SERVICE_URL"),
    ("java", "JAVA_SERVICE_URL"),
    ("php", "PHP_SERVICE_URL"),
)


class TodosLosMicroserviciosFallaron(Exception):
    """Se lanza cuando ningun microservicio sirvio la lista de equipos.

    No es un error para el usuario: la vista la atrapa y cae al ORM. Existencia
    para que el log y los tests puedan distinguir "no hay equipos" (lista vacia,
    exito) de "no pude leer en ningun lado" (todos caidos).
    """


def _normalizar_equipos(datos):
    """Convierte la respuesta JSON de un microservicio en objetos Equipo.

    Los tres servicios devuelven la misma forma:
        {"equipos": [{"id": 1, "nombre": "...", "tipo": "laptop", "disponible": true}]}

    Se construyen instancias de `Equipo` SIN guardar para que el template reciba
    exactamente los mismos objetos que si se hubiera leido del ORM: asi
    `lista_equipos.html` sigue usando `equipo.get_tipo_display` y los `{% url %}`
    con `equipo.id` sin tocar una linea, y el context no depende del origen del
    dato.

    `tipo` llega como clave ("laptop"), no como etiqueta, y `get_tipo_display()`
    la traduce. Esa es la razon por la que los tres servicios devuelven la clave:
    un microservicio no deberia decidir como se muestra un tipo en otro idioma.

    @param dict datos JSON ya parseado.
    @param list[Equipo] modelo referencia (importado diferido para evitar un
        import circular con `inventario.models`).
    @returns list
    @raises ValueError si la forma no es la esperada.
    """
    # Import diferido: `models.py` no importa este modulo, pero importarlo arriba
    # del todo hace que el modulo dependa del app en tiempo de importacion.
    from .models import Equipo

    if not isinstance(datos, dict) or "equipos" not in datos:
        raise ValueError("La respuesta no trae la clave 'equipos'.")

    filas = datos["equipos"]
    if not isinstance(filas, list):
        raise ValueError("'equipos' no es una lista.")

    equipos = []
    for fila in filas:
        if not isinstance(fila, dict):
            raise ValueError("Un equipo de la lista no es un objeto.")

        # Sin esto, un id que venga como texto ("7") se filtraria al context y el
        # orden por id del template seria lexicografico ("10" antes que "2"). Los
        # microservicios devuelven id numerico, pero el casteo deja el context
        # consistente sin depender de eso.
        equipos.append(
            Equipo(
                id=int(fila["id"]),
                nombre=str(fila["nombre"]),
                tipo=str(fila["tipo"]),
                disponible=bool(fila["disponible"]),
            )
        )
    return equipos


def _leer_de_un_microservicio(nombre, url_base):
    """Intenta leer la lista en UN microservicio.

    @param str nombre etiqueta para logs ("node", "java", "php").
    @param str url_base URL base del servicio.
    @returns list[Equipo]
    @raises Exception si hay que pasar al siguiente de la cadena. Se atrapa
        cualquier excepcion a proposito: el objetivo es que esta funcion nunca
        propague errores, porque un fallo de red es un resultado mas de la
        lectura, no una excepcion que deba tumbar la pagina.
    """
    url = f"{url_base.rstrip('/')}/equipos"

    try:
        respuesta = requests.get(url, timeout=settings.TIMEOUT_MICROSERVICIOS)

        if respuesta.status_code >= 500:
            raise RuntimeError(
                f"respondio con el estado {respuesta.status_code}"
            )

        if respuesta.status_code != 200:
            # Un 4xx significa que el servicio contesto: no se avanza al
            # siguiente, porque el siguiente daria lo mismo y solo se taparia el
            # problema real.
            raise requests.exceptions.HTTPError(
                f"respondio con el estado {respuesta.status_code}: "
                f"{respuesta.text[:200]}"
            )

        # `.json()` levanta ValueError si el cuerpo no es JSON. Un servicio que
        # devuelve HTML (por ejemplo la pagina de error de un proxy) cae aqui.
        datos = respuesta.json()

        equipos = _normalizar_equipos(datos)

    except requests.exceptions.Timeout:
        logger.warning(
            "El microservicio %s (%s) tardo mas de %ss: se prueba el siguiente.",
            nombre,
            url,
            settings.TIMEOUT_MICROSERVICIOS,
        )
        raise
    except requests.exceptions.ConnectionError as exc:
        logger.warning(
            "No se pudo conectar con el microservicio %s (%s): %s",
            nombre,
            url,
            exc,
        )
        raise
    except ValueError as exc:
        # JSON invalido o forma inesperada: el servicio respondio pero no sirvio
        # el dato que se le pidio.
        logger.warning(
            "El microservicio %s (%s) devolvio una respuesta no valida: %s",
            nombre,
            url,
            exc,
        )
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Fallo inesperado consultando el microservicio %s (%s): %s",
            nombre,
            url,
            exc,
        )
        raise

    logger.info(
        "Equipos leidos del microservicio %s (%s): %d equipos.",
        nombre,
        url,
        len(equipos),
    )
    return equipos


def leer_equipos_desde_microservicios():
    """Recorre la cadena Node -> Java -> PHP y devuelve la primera lectura buena.

    @returns tuple (list[Equipo], str) los equipos y el nombre del microservicio
        que los sirvio ("node", "java" o "php"). El nombre se devuelve junto con
        los datos para NO tener que adivinarlo despues, que obligaria a repetir
        la peticion HTTP.
    @raises TodosLosMicroserviciosFallaron si ninguno respondio.
    """
    for nombre, atributo_url in CADENA_DE_LECTURA:
        url_base = getattr(settings, atributo_url, "")
        if not url_base:
            logger.warning(
                "El microservicio %s no tiene URL configurada (%s vacio): se omite.",
                nombre,
                atributo_url,
            )
            continue
        url_base = normalizar_url_servicio(url_base)

        try:
            return _leer_de_un_microservicio(nombre, url_base), nombre
        except Exception:  # noqa: BLE001
            # `_leer_de_un_microservicio` ya logueo el motivo; aqui solo se sigue
            # con el siguiente de la cadena.
            continue

    raise TodosLosMicroserviciosFallaron(
        "Ninguno de los tres microservicios de equipos respondio."
    )


def leer_equipos():
    """Punto de entrada unico para leer el inventario, con toda la resiliencia.

    Es la funcion que la vista llama. Intenta los tres microservicios y, si los
    tres fallan, cae a la base de Django y lo deja asentado en el log con nivel
    ERROR, que es la unica señal de que la cadena entera esta caida.

    @returns tuple (list[Equipo], str) la lista y de donde salio ("node",
        "java", "php", "orm" o "orm-sin-microservicios"). El origen se devuelve
        para poder mostrarlo y probarlo, no solo para que quede en el log.
    """
    try:
        equipos, origen = leer_equipos_desde_microservicios()
    except TodosLosMicroserviciosFallaron:
        equipos = list(_leer_desde_el_orm())
        logger.error(
            "Los 3 microservicios de equipos (node, java, php) fallaron. "
            "La lista se muestra desde el ORM de Django con %d equipos.",
            len(equipos),
        )
        return equipos, "orm-sin-microservicios"

    return equipos, origen


def _leer_desde_el_orm():
    """Ultimo recurso: los equipos desde la base de Django.

    `order_by("id")` para que el listado salga en el mismo orden que el de los
    microservicios. Sin esto, Postgres podria devolver las filas en otro orden y
    la lista cambiaria de orden segun de donde venga el dato.
    """
    from .models import Equipo

    return Equipo.objects.all().order_by("id")
