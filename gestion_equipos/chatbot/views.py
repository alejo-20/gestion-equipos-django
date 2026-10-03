import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import gemini, services
from .models import Conversacion, Mensaje

logger = logging.getLogger(__name__)

# Protecciones economicas. El tope duro de llamadas a la API por turno esta en
# services.MAX_ITERACIONES; esto es la red exterior para un bucle del frontend.
MAX_LONGCUD = 500
MAX_MENSAJES_POR_MINUTO = 10
VENTANA_LIMITE = 60  # segundos

CLAVE_SESION = "chatbot_conversacion_id"


def _obtener_conversacion(request):
    """Devuelve la conversacion de esta sesion de Django, creandola si falta.

    El id se guarda dentro de la sesion a proposito: ademas de evitar una
    consulta, mantiene la sesion "no vacia". Django solo envia la cookie de
    sesion cuando la sesion tiene datos, asi que crear la sesion sin guardar
    nada haria que se perdiera y cada peticion abriria una conversacion nueva.
    """
    conversacion = None

    id_guardado = request.session.get(CLAVE_SESION)
    if id_guardado:
        conversacion = Conversacion.objects.filter(pk=id_guardado).first()

    if conversacion is None:
        conversacion = Conversacion.objects.create(
            session_key=request.session.session_key or ""
        )
        request.session[CLAVE_SESION] = conversacion.id

    return conversacion


def _excedio_el_limite(request):
    """Cuenta los intentos en la cache, indexados por IP.

    Cuenta intentos y no mensajes guardados porque un turno fallido se borra
    del historial: si se contaran los mensajes, un bucle de peticiones fallidas
    (por ejemplo con la API key mal puesta) nunca llegaria al limite.

    Se indexa por IP y no por sesion para que el limite tambien aplique si el
    cliente no acepta cookies.
    """
    ip = request.META.get("REMOTE_ADDR", "desconocida")
    clave = f"chatbot:limite:{ip}"
    enviados = cache.get(clave, 0) + 1
    cache.set(clave, enviados, VENTANA_LIMITE)
    return enviados > MAX_MENSAJES_POR_MINUTO


def chat(request):
    # Patron vista -> modelo -> context -> template.
    context = {
        "conversacion": _obtener_conversacion(request),
        "mensajes": Mensaje.objects.none(),
        "api_habilitada": gemini.hay_api_key(),
    }
    return render(request, "chatbot/chat.html", context)


@require_POST
def api_mensaje(request):
    """Recibe un mensaje del usuario y devuelve la respuesta del asistente."""
    texto = (request.POST.get("mensaje") or "").strip()

    if not texto:
        return JsonResponse({"error": "Escribe un mensaje."}, status=400)

    if len(texto) > MAX_LONGCUD:
        return JsonResponse(
            {"error": f"El mensaje no puede superar los {MAX_LONGCUD} caracteres."},
            status=400,
        )

    if _excedio_el_limite(request):
        return JsonResponse(
            {"error": "Vas muy rapido. Espera un momento antes de seguir."},
            status=429,
        )

    conversacion = _obtener_conversacion(request)

    mensaje_usuario = Mensaje.objects.create(
        conversacion=conversacion, rol="user", texto=texto
    )

    try:
        respuesta, pasos = services.responder(conversacion, texto)
    except gemini.ErrorGemini as exc:
        # Se borra el mensaje del usuario para no dejar un turno a medias: dos
        # user_input seguidos sin respuesta romperian la reconstruccion del
        # historial.
        mensaje_usuario.delete()
        logger.warning("Error de Gemini en el chat: %s", exc)
        return JsonResponse({"error": str(exc)}, status=503)

    Mensaje.objects.create(
        conversacion=conversacion,
        rol="bot",
        texto=respuesta,
        pasos=pasos,
    )

    return JsonResponse({"respuesta": respuesta})
