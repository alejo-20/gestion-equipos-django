from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from .models import Conversacion, Mensaje
from .services import _pasos_de_mensajes, _recortar
from .tools import FUNCIONES, HERRAMIENTAS


def _respuesta_api(payload, status_code=200):
    """Fake de requests.get() que devuelve un JSON como el de /api/."""
    respuesta = MagicMock()
    respuesta.status_code = status_code
    respuesta.json.return_value = payload
    return respuesta


class HistorialTests(TestCase):
    def setUp(self):
        self.conversacion = Conversacion.objects.create(session_key="test")

    def test_reconstruye_historial_alternando_usuario_y_bot(self):
        Mensaje.objects.create(
            conversacion=self.conversacion, rol="user", texto="hola"
        )
        Mensaje.objects.create(
            conversacion=self.conversacion,
            rol="bot",
            texto="buenas",
            pasos=[{"type": "model_output", "content": []}],
        )

        historial = _pasos_de_mensajes(self.conversacion.mensajes.all())

        self.assertEqual(len(historial), 2)
        self.assertEqual(historial[0]["type"], "user_input")
        self.assertEqual(historial[0]["content"][0]["text"], "hola")
        self.assertEqual(historial[1]["type"], "model_output")

    def test_recortar_conserva_solo_los_ultimos_turnos(self):
        for i in range(6):
            Mensaje.objects.create(
                conversacion=self.conversacion, rol="user", texto=f"pregunta {i}"
            )
            Mensaje.objects.create(
                conversacion=self.conversacion, rol="bot", texto=f"respuesta {i}"
            )

        historial = _recortar(
            _pasos_de_mensajes(self.conversacion.mensajes.all()), turnos=2
        )

        textos = [p["content"][0]["text"] for p in historial if p["type"] == "user_input"]
        self.assertEqual(textos, ["pregunta 4", "pregunta 5"])


class ToolsTests(TestCase):
    def setUp(self):
        from inventario.models import Equipo
        from prestamos.models import Prestamo

        # La migracion 0002_seed_equipos deja equipos en la base, asi que los
        # tests se apoyan en el equipo creado aqui y no en conteos absolutos.
        self.equipo = Equipo.objects.create(nombre="Laptop Test", tipo="laptop")
        # Se replica lo que hace prestamos.views.prestar_equipo al crear el prestamo.
        self.equipo.disponible = False
        self.equipo.save()
        self.prestamo = Prestamo.objects.create(
            equipo=self.equipo, nombre_persona="Ana Diaz"
        )

    def test_consultar_equipos_pide_los_equipos_al_endpoint_publico(self):
        """La tool tiene que leer /api/equipos/ por HTTP, no el ORM.

        Si esto se rompe y vuelve a leer el ORM, el chatbot deja de depender del
        endpoint publico, que es justamente lo que la actividad quiere mostrar.
        """
        from . import tools

        with patch("chatbot.tools.requests.get") as get:
            get.return_value = _respuesta_api(
                {
                    "equipos": [
                        {
                            "id": 1,
                            "nombre": "Laptop Test",
                            "tipo": "Laptop",
                            "disponible": False,
                        }
                    ]
                }
            )
            resultado = tools.consultar_equipos(tipo="laptop", disponible=False)

        url = get.call_args.args[0]
        params = get.call_args.kwargs["params"]
        self.assertEqual(url, f"{settings.API_BASE_URL}/api/equipos/")
        self.assertEqual(params, {"tipo": "laptop", "disponible": "false"})
        self.assertEqual(resultado["cantidad"], 1)
        self.assertEqual(resultado["equipos"][0]["tipo"], "Laptop")
        self.assertEqual(resultado["equipos"][0]["nombre"], "Laptop Test")

    def test_consultar_prestamos_por_defecto_pide_solo_activos(self):
        from . import tools

        with patch("chatbot.tools.requests.get") as get:
            get.return_value = _respuesta_api(
                {
                    "prestamos": [
                        {
                            "id": 1,
                            "equipo_id": 1,
                            "equipo": "Laptop Test",
                            "nombre_persona": "Ana Diaz",
                            "fecha_prestamo": "2026-01-01T10:00:00+00:00",
                            "fecha_devolucion": None,
                            "devuelto": False,
                        }
                    ]
                }
            )
            resultado = tools.consultar_prestamos()

        self.assertEqual(get.call_args.args[0], f"{settings.API_BASE_URL}/api/prestamos/")
        self.assertEqual(get.call_args.kwargs["params"], {"estado": "activo"})
        self.assertEqual(resultado["estado"], "activo")
        self.assertEqual(resultado["cantidad"], 1)
        # El endpoint dice "nombre_persona"; el modelo ya conoce "persona".
        self.assertEqual(resultado["prestamos"][0]["persona"], "Ana Diaz")
        self.assertEqual(resultado["prestamos"][0]["equipo_id"], 1)

    def test_consultar_prestamos_manda_el_filtro_de_persona(self):
        from . import tools

        with patch("chatbot.tools.requests.get") as get:
            get.return_value = _respuesta_api({"prestamos": []})
            tools.consultar_prestamos(estado="devuelto", persona="  Ana  ")

        self.assertEqual(
            get.call_args.kwargs["params"], {"estado": "devuelto", "persona": "Ana"}
        )

    def test_consultar_equipos_devuelve_error_si_la_api_no_responde(self):
        """Un error de red es un resultado de la tool, nunca una excepcion."""
        import requests as requests_real

        from . import tools

        with patch(
            "chatbot.tools.requests.get",
            side_effect=requests_real.exceptions.ConnectionError,
        ):
            resultado = tools.consultar_equipos()

        self.assertIn("error", resultado)
        self.assertNotIn("equipos", resultado)

    def test_consultar_prestamos_devuelve_error_si_la_api_responde_500(self):
        from . import tools

        with patch("chatbot.tools.requests.get") as get:
            get.return_value = _respuesta_api({}, status_code=500)
            resultado = tools.consultar_prestamos()

        self.assertIn("error", resultado)
        self.assertIn("500", resultado["error"])

    def test_consultar_equipos_rechaza_tipo_invalido(self):
        from . import tools

        with patch("chatbot.tools.requests.get") as get:
            resultado = tools.consultar_equipos(tipo="avion")

        # Se valida antes de pegarle al endpoint, asi que ni se llama.
        self.assertIn("error", resultado)
        get.assert_not_called()

    def test_consultar_equipo_marca_prestado_a(self):
        from . import tools

        resultado = tools.consultar_equipo(self.equipo.id)

        self.assertEqual(resultado["equipo"]["prestado_a"], "Ana Diaz")
        self.assertFalse(resultado["equipo"]["disponible"])
        self.assertIsNotNone(resultado["equipo"]["fecha_prestamo"])

    def test_consultar_equipo_inexistente_devuelve_error(self):
        from . import tools

        resultado = tools.consultar_equipo(9999)

        self.assertIn("error", resultado)

    def test_consultar_equipo_se_basa_en_el_prestamo_y_no_en_el_flag(self):
        """La fuente de verdad es la tabla Prestamo, no `Equipo.disponible`.

        Si el flag quedo desincronizado (borraste un prestamo, editaste uno ya
        devuelto, toco la base por fuera...), leer el flag hacia que el chatbot
        dijera "nadie lo tiene" de un equipo que si tiene un prestamo activo.
        """
        from . import tools

        # El flag queda deliberadamente en True: el prestamo activo es real.
        self.equipo.disponible = True
        self.equipo.save()

        resultado = tools.consultar_equipo(self.equipo.id)

        self.assertEqual(resultado["equipo"]["prestado_a"], "Ana Diaz")
        self.assertFalse(resultado["equipo"]["disponible"])
        self.assertIsNotNone(resultado["equipo"]["fecha_prestamo"])

    def test_consultar_equipo_ignora_los_prestamos_ya_devueltos(self):
        from . import tools

        from prestamos.models import Prestamo

        self.prestamo.devuelto = True
        self.prestamo.save()
        Prestamo.objects.create(
            equipo=self.equipo, nombre_persona="Bruno Soto", devuelto=True
        )

        resultado = tools.consultar_equipo(self.equipo.id)

        self.assertIsNone(resultado["equipo"]["prestado_a"])
        self.assertIsNone(resultado["equipo"]["fecha_prestamo"])
        self.assertTrue(resultado["equipo"]["disponible"])

    def test_consultar_equipo_toma_el_prestamo_activo_mas_reciente(self):
        from . import tools

        from prestamos.models import Prestamo

        # Dos activos por error de carga: gana el mas reciente.
        self.prestamo.fecha_prestamo = "2026-01-01T10:00:00+00:00"
        self.prestamo.nombre_persona = "Ana Diaz"
        self.prestamo.save()
        Prestamo.objects.create(equipo=self.equipo, nombre_persona="Bruno Soto")

        resultado = tools.consultar_equipo(self.equipo.id)

        self.assertEqual(resultado["equipo"]["prestado_a"], "Bruno Soto")

    def test_el_flag_desincronizado_no_toca_la_api_de_prestamos(self):
        """/api/prestamos/ tampoco se apoya en el flag: lee la tabla Prestamo."""
        import json

        from django.test import Client

        from prestamos.models import Prestamo

        self.equipo.disponible = True
        self.equipo.save()
        prestamo = Prestamo.objects.filter(devuelto=False).first()
        prestamo.devuelto = True
        prestamo.save()

        # Cliente real (no el de test) para pegarle a la URL publica.
        datos = json.loads(
            Client().get("/api/prestamos/", {"estado": "activo"}).content
        )

        self.assertEqual(datos["prestamos"], [])

    def test_ejecutar_ignora_argumentos_desconocidos(self):
        from . import tools

        resultado = tools.ejecutar("consultar_equipos", {"inexistente": 1})

        self.assertIn("error", resultado)

    def test_ejecutar_herramienta_inexistente(self):
        from . import tools

        resultado = tools.ejecutar("borrar_todo", {})

        self.assertIn("error", resultado)


class VistaChatTests(TestCase):
    def setUp(self):
        from . import gemini

        # El limite se guarda en la cache por IP y la cache es compartida por
        # todo el proceso, asi que hay que limpiarla entre tests.
        cache.clear()
        # gemini.py cachea el cliente en una variable de modulo. Si un test lo
        # crea con la key real, los tests que esperan "sin API key" fallarian
        # por orden de ejecucion.
        gemini._cliente = None

    def test_endpoint_responde_error_claro_sin_api_key(self):
        from . import gemini

        with override_settings(GEMINI_API_KEY=""):
            respuesta = self.client.post(
                "/chatbot/api/mensaje/", {"mensaje": "hola"}
            )
            # La comprobacion va dentro del override_settings: fuera leeria la
            # key real del entorno y el test pasaria por casualidad.
            self.assertFalse(gemini.hay_api_key())

        self.assertEqual(respuesta.status_code, 503)
        self.assertIn("GEMINI_API_KEY", respuesta.json()["error"])

    def test_turno_a_medias_se_borra_si_gemini_falla(self):
        from . import gemini

        with override_settings(GEMINI_API_KEY=""):
            self.client.post("/chatbot/api/mensaje/", {"mensaje": "hola"})

        # Un user_input sin respuesta romperia la reconstruccion del historial.
        self.assertEqual(Mensaje.objects.count(), 0)

    def test_rechaza_mensaje_vacio(self):
        respuesta = self.client.post("/chatbot/api/mensaje/", {"mensaje": "   "})

        self.assertEqual(respuesta.status_code, 400)

    def test_rechaza_mensaje_demasiado_largo(self):
        respuesta = self.client.post("/chatbot/api/mensaje/", {"mensaje": "x" * 501})

        self.assertEqual(respuesta.status_code, 400)

    def test_endpoint_solo_acepta_post(self):
        respuesta = self.client.get("/chatbot/api/mensaje/")

        self.assertEqual(respuesta.status_code, 405)

    def test_limita_las_peticiones_por_minuto(self):
        codigos = []
        for i in range(11):
            with override_settings(GEMINI_API_KEY=""):
                respuesta = self.client.post(
                    "/chatbot/api/mensaje/", {"mensaje": f"pregunta {i}"}
                )
            codigos.append(respuesta.status_code)

        # Los 10 primeros se procesan (503 por falta de key) y el 11o se corta.
        self.assertEqual(codigos[:10], [503] * 10)
        self.assertEqual(codigos[10], 429)

    def test_guarda_turno_completo_cuando_gemini_responde(self):
        with override_settings(GEMINI_API_KEY="clave-de-prueba"):
            with patch("chatbot.services.gemini.crear_interaccion") as crear:
                interaccion = MagicMock()
                interaccion.steps = [
                    SimpleNamespace(
                        type="model_output",
                        model_dump=lambda: {"type": "model_output", "content": []},
                    )
                ]
                interaccion.output_text = "Hay 6 equipos."
                crear.return_value = interaccion

                respuesta = self.client.post(
                    "/chatbot/api/mensaje/", {"mensaje": "cuantos equipos hay"}
                )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["respuesta"], "Hay 6 equipos.")
        self.assertEqual(Mensaje.objects.filter(rol="user").count(), 1)
        self.assertEqual(Mensaje.objects.filter(rol="bot").count(), 1)


class DeclaracionesDeHerramientasTests(SimpleTestCase):
    """Contrato entre tools.py y la Interactions API.

    Estos tests existen por un bug concreto: se usaba el formato anidado de la
    API legacy (`{"type": "function", "function": {...}}`) y la API real
    respondia `400 Missing name in function tool`. La suite completa pasaba
    porque todos los tests mockean `crear_interaccion`, asi que el formato nunca
    llegaba a la API. Estos tests lo validan sin gastar una llamada.
    """

    def test_usa_el_formato_plano_de_la_interactions_api(self):
        for declaracion in HERRAMIENTAS:
            with self.subTest(tool=declaracion.get("name")):
                self.assertEqual(declaracion["type"], "function")
                # El nombre va en el primer nivel. El formato legacy lo anidaba
                # dentro de "function" y por eso el nombre no llegaba.
                self.assertIn("name", declaracion)
                self.assertNotIn("function", declaracion)

    def test_cada_tool_tiene_nombre_descripcion_y_esquema(self):
        for declaracion in HERRAMIENTAS:
            with self.subTest(tool=declaracion["name"]):
                self.assertTrue(declaracion["name"])
                self.assertTrue(declaracion["description"].strip())
                # JSON Schema del estilo draft usado por la API.
                self.assertEqual(declaracion["parameters"]["type"], "object")
                self.assertIsInstance(declaracion["parameters"]["properties"], dict)
                for obligatorio in declaracion["parameters"].get("required", []):
                    self.assertIn(
                        obligatorio,
                        declaracion["parameters"]["properties"],
                        f"'{obligatorio}' es required pero no esta en properties",
                    )

    def test_los_primeros_parametros_deben_pasar(self):
        """Si la API anade required, el `Function` del SDK deja de validar."""
        from google.genai._gaos.types.interactions.function import Function

        for declaracion in HERRAMIENTAS:
            with self.subTest(tool=declaracion["name"]):
                Function.model_validate(declaracion)

    def test_declara_exactamente_las_tools_implementadas(self):
        declaradas = {d["name"] for d in HERRAMIENTAS}
        # Si se implementa una tool nueva hay que declararla, y al reves: el
        # modelo solo puede invocar lo que aparece en HERRAMIENTAS.
        self.assertEqual(declaradas, set(FUNCIONES))
        self.assertEqual(len(declaradas), len(HERRAMIENTAS), "hay nombres duplicados")

    def test_los_parametros_declarados_coinciden_con_la_funcion_real(self):
        """Si no coinciden, `ejecutar` falla en runtime con TypeError.

        El modelo decide que argumentos enviar leyendo `parameters`, asi que una
        discrepancia con la firma real solo se descubre cuando el usuario
        pregunta justo lo que la dispara.
        """
        import inspect

        for declaracion in HERRAMIENTAS:
            with self.subTest(tool=declaracion["name"]):
                firma = inspect.signature(FUNCIONES[declaracion["name"]])
                declarados = declaracion["parameters"]["properties"]
                requeridos = set(declaracion["parameters"].get("required", []))

                self.assertEqual(set(declarados), set(firma.parameters))

                for nombre, parametro in firma.parameters.items():
                    tiene_default = parametro.default is not inspect.Parameter.empty
                    # Un argumento opcional se declara como opcional, y al reves:
                    # marcar como required algo que tiene default es confuso.
                    self.assertEqual(
                        nombre in requeridos,
                        not tiene_default,
                        f"'{nombre}' y su default no coinciden con 'required'",
                    )

    def test_estado_solo_admite_valores_de_filtro(self):
        """`estado` es un filtro de lectura, nunca una orden de cambio de estado."""
        declaracion = next(d for d in HERRAMIENTAS if d["name"] == "consultar_prestamos")
        enum = declaracion["parameters"]["properties"]["estado"]["enum"]
        self.assertEqual(set(enum), {"activo", "devuelto"})
