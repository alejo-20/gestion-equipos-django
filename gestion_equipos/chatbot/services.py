"""Orquesta la conversacion: historial, loop de herramientas y persistencia.

El modelo nunca escribe en la base de datos. Este servicio solo:
  1. Reconstruye el historial desde los mensajes guardados.
  2. Llama a Gemini.
  3. Si el modelo pide datos, ejecuta la herramienta y le devuelve el resultado.
  4. Repite hasta obtener texto, y guarda el turno.
"""

import json
import logging

from . import gemini, tools

logger = logging.getLogger(__name__)

# Tope de vueltas tool -> modelo. Evita que una tool rota genere un bucle
# infinito y una factura inesperada.
MAX_ITERACIONES = 6

# Cuantos turnos (par usuario/asistente) se reenvian a Gemini. El modelo no
# necesita la conversacion completa para responder sobre el inventario.
MAX_TURNOS_HISTORIAL = 10

INSTRUCCION_SISTEMA = """\
Eres el asistente virtual de "Gestion de Equipos", una aplicacion interna de una
oficina que controla el inventario de equipos tecnologicos y los prestamos.

Reglas:
- Responde siempre en espanol, de forma breve y clara.
- Tienes unicamente informacion de inventario y prestamos. No inventes datos:
  si necesitas un dato, llama a una herramienta. Si ninguna herramienta te da la
  informacion, di que no la tienes.
- Para responder, usa las herramientas. No adivines ids de equipo ni nombres de
  personas.
- Si una herramienta devuelve un error, explica el problema al usuario de forma
  sencilla en vez de mostrar el error tecnico.
- No puedes registrar prestamos ni devoluciones: solo informas. Si te lo piden,
  di que deben hacerlo desde el sitio web.
- Si la pregunta es ambigua y podrias responder de varias formas, pregunta.
"""


def _pasos_de_mensajes(mensajes):
    """Reconstruye la lista de steps de la conversacion.

    Alterna steps de `user_input` (desde el texto guardado) con los steps crudos
    que devolvio Gemini en cada turno. Los steps se reenvian sin modificar
    porque contienen las thought signatures que la API exige.
    """
    historial = []
    for mensaje in mensajes:
        if mensaje.rol == "user":
            historial.append(
                {
                    "type": "user_input",
                    "content": [{"type": "text", "text": mensaje.texto}],
                }
            )
        else:
            historial.extend(mensaje.pasos)
    return historial


def _recortar(historial, turnos=MAX_TURNOS_HISTORIAL):
    """Deja solo los ultimos `turnos` turnos, alineado en un user_input."""
    if turnos <= 0:
        return []
    indices = [i for i, paso in enumerate(historial) if paso.get("type") == "user_input"]
    if len(indices) <= turnos:
        return historial
    return historial[indices[-turnos]:]


def responder(conversacion, texto_usuario):
    """Responde un turno de conversacion.

    Devuelve (texto, pasos_del_turno). Los pasos se guardan tal cual los
    devolvio la API para poder reproducir el hilo en la siguiente vuelta.
    """
    historial = _recortar(_pasos_de_mensajes(conversacion.mensajes.all()))
    historial.append(
        {
            "type": "user_input",
            "content": [{"type": "text", "text": texto_usuario}],
        }
    )

    pasos_del_turno = []

    for _ in range(MAX_ITERACIONES):
        interaccion = gemini.crear_interaccion(
            historial,
            tools.HERRAMIENTAS,
            INSTRUCCION_SISTEMA,
        )

        nuevos = [paso.model_dump() for paso in interaccion.steps]
        # La respuesta puede venir con el user_input ya incluido; se filtra
        # para no duplicarlo en el historial.
        nuevos = [paso for paso in nuevos if paso.get("type") != "user_input"]
        pasos_del_turno.extend(nuevos)

        llamadas = [paso for paso in interaccion.steps if paso.type == "function_call"]

        if not llamadas:
            texto = (interaccion.output_text or "").strip()
            if not texto:
                texto = "No pude generar una respuesta. Intenta de nuevo."
            return texto, pasos_del_turno

        historial.extend(nuevos)

        for llamada in llamadas:
            resultado = tools.ejecutar(llamada.name, llamada.arguments)
            logger.info("Herramienta %s(%s)", llamada.name, llamada.arguments)
            paso_resultado = {
                "type": "function_result",
                "name": llamada.name,
                "call_id": llamada.id,
                "result": [
                    {
                        "type": "text",
                        "text": json.dumps(resultado, ensure_ascii=False, default=str),
                    }
                ],
            }
            historial.append(paso_resultado)
            pasos_del_turno.append(paso_resultado)

    return (
        "La consulta necesito demasiados pasos para responder. Prueba a "
        "reformular la pregunta de forma mas especifica.",
        pasos_del_turno,
    )
