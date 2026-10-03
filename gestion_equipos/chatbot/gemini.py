"""Capa de transporte hacia la API de Gemini.

Este es el UNICO modulo del proyecto que importa `google.genai`. Aislar el SDK
aqui permite cambiar de modelo, de SDK o de API (Interactions API hoy, otra
mañana) sin tocar ni las vistas ni el loop de herramientas.

La Interactions API es la interfaz recomendada por Google desde junio de 2026;
`generateContent` queda como API legacy. Se usa `store=False` porque el estado
de la conversacion vive en la base de datos del proyecto, no en el servidor de
Google.
"""

import logging

from django.conf import settings
from google import genai
from google.genai import errors

logger = logging.getLogger(__name__)

_cliente = None


class ErrorGemini(Exception):
    """Error de la API de Gemini con un mensaje ya listo para mostrar al usuario."""


def _mensaje_amigable(exc):
    """Traduce los errores de la API a mensajes en español."""
    codigo = getattr(exc, "code", None)
    detalle = str(exc)

    if codigo == 400 and "API_KEY_INVALID" in detalle:
        return (
            "La API key de Gemini no es valida. Revisa GEMINI_API_KEY en el "
            "archivo .env."
        )
    if codigo == 400 and "API_KEY_MISSING" in detalle:
        return "No hay API key de Gemini configurada (variable GEMINI_API_KEY)."
    if codigo == 403:
        return (
            "La API key de Gemini no tiene permiso para usar este modelo. "
            "Puede que el modelo no este disponible en el plan gratuito."
        )
    if codigo == 404:
        return (
            f"El modelo '{settings.GEMINI_MODEL}' no existe o no esta disponible "
            "para esta API key. Prueba con otro valor en GEMINI_MODEL."
        )
    if codigo == 429:
        return (
            "Se alcanzo el limite de solicitudes de Gemini. Espera unos "
            "segundos e intenta de nuevo."
        )
    if codigo >= 500:
        return "El servicio de Gemini esta temporalmente fuera de servicio."

    return f"Ocurrio un error al consultar Gemini: {detalle}"


def _obtener_cliente():
    global _cliente
    if _cliente is None:
        api_key = (settings.GEMINI_API_KEY or "").strip()
        if not api_key:
            raise ErrorGemini(
                "El chatbot no esta configurado: falta la variable GEMINI_API_KEY "
                "en el archivo .env."
            )
        _cliente = genai.Client(api_key=api_key)
    return _cliente


def hay_api_key():
    """True si existe una API key configurada (para avisar en la interfaz)."""
    return bool((settings.GEMINI_API_KEY or "").strip())


def crear_interaccion(entrada, herramientas, instruccion_sistema):
    """Envia una interaccion a Gemini y devuelve el objeto Interaction.

    `entrada` es la lista de steps del historial mas el nuevo turno del usuario.
    Los errores del SDK se convierten en ErrorGemini con mensaje en español para
    que las vistas no tengan que conocer la API.
    """
    cliente = _obtener_cliente()
    try:
        return cliente.interactions.create(
            model=settings.GEMINI_MODEL,
            input=entrada,
            tools=herramientas,
            system_instruction=instruccion_sistema,
            store=False,
        )
    except errors.APIError as exc:
        logger.warning("Error de la API de Gemini: %s", exc)
        raise ErrorGemini(_mensaje_amigable(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - red o SDK: mensaje generico, no filtrar detalle interno
        logger.exception("Fallo inesperado al llamar a Gemini")
        raise ErrorGemini(f"No se pudo completar la consulta: {exc}") from exc
