"""Tests de la lectura resiliente (Node -> Java -> PHP -> ORM) y de los tres
botones de guardado.

Estos tests NO levantan los microservicios: `requests` va simulado. Lo que se
verifica es la POLITICA de la cadena (a quien se le pregunta primero, cuando se
avanza al siguiente y cuando se cae al ORM) y no que los servicios anden. Que los
tres sirvan de verdad se comprueba levantandolos, que es lo que dice el README.
"""

from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Equipo
from .resiliencia import leer_equipos
from .servicios_equipos import guardar_equipo_en_microservicio


def respuesta_falsa(status_code=200, cuerpo=None):
    """Arma un objeto con la misma forma que devuelve `requests.get`.

    Se usa un `mock.Mock` y no la clase real de requests justamente para no
    atarse a su implementacion: si solo se usan `.status_code`, `.json()` y
    `.text`, alcanza con eso.
    """
    respuesta = mock.Mock()
    respuesta.status_code = status_code
    respuesta.json.return_value = cuerpo if cuerpo is not None else {"equipos": []}
    respuesta.text = str(cuerpo)
    return respuesta


def fila(id, nombre, tipo="laptop", disponible=True):
    return {"id": id, "nombre": nombre, "tipo": tipo, "disponible": disponible}


class LecturaResilienteTests(TestCase):
    """La cadena de lectura: Node, luego Java, luego PHP, y al final el ORM."""

    def setUp(self):
        # La migracion 0002 deja equipos en la base, asi que los tests crean los
        # suyos y no dependen de conteos absolutos.
        self.laptop = Equipo.objects.create(nombre="Notebook Siamesa", tipo="laptop")

    @mock.patch("inventario.resiliencia.requests.get")
    def test_consulta_primero_al_microservicio_node(self, get):
        """Con los tres(andando, gana Node: es el mas rapido."""
        get.return_value = respuesta_falsa(
            cuerpo={"equipos": [fila(1, "Desde Node")]}
        )

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "node")
        self.assertEqual([e.nombre for e in equipos], ["Desde Node"])
        # Y se le pregunta SOLO a el: si se hubiera consultado a los demas, la
        # cadena estaria mal y seria mas lenta de lo necesario.
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], settings.NODE_SERVICE_URL + "/equipos")

    @mock.patch("inventario.resiliencia.requests.get")
    def test_cae_a_java_si_node_no_responde(self, get):
        """Node con conexion rechazada: el siguiente de la cadena es Java."""
        get.side_effect = [
            __import__("requests").exceptions.ConnectionError("node caido"),
            respuesta_falsa(cuerpo={"equipos": [fila(1, "Desde Java")]}),
        ]

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "java")
        self.assertEqual([e.nombre for e in equipos], ["Desde Java"])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[1].args[0], settings.JAVA_SERVICE_URL + "/equipos")

    @mock.patch("inventario.resiliencia.requests.get")
    def test_cae_a_java_si_node_devuelve_500(self, get):
        """Un 5xx tambien hace avanzar: el servicio esta, pero no puede leer."""
        get.side_effect = [
            respuesta_falsa(status_code=500, cuerpo={"error": "base caida"}),
            respuesta_falsa(cuerpo={"equipos": [fila(1, "Desde Java")]}),
        ]

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "java")
        self.assertEqual([e.nombre for e in equipos], ["Desde Java"])

    @mock.patch("inventario.resiliencia.requests.get")
    def test_cae_a_php_si_node_y_java_fallan(self, get):
        """Los dos primeros caidos: el ultimo de la cadena es PHP."""
        get.side_effect = [
            __import__("requests").exceptions.Timeout("node tardo"),
            __import__("requests").exceptions.ConnectionError("java caido"),
            respuesta_falsa(cuerpo={"equipos": [fila(1, "Desde PHP")]}),
        ]

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "php")
        self.assertEqual([e.nombre for e in equipos], ["Desde PHP"])
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args.args[0], settings.PHP_SERVICE_URL + "/equipos")

    @mock.patch("inventario.resiliencia.requests.get")
    def test_cae_al_orm_si_los_tres_fallan(self, get):
        """Los tres caidos: el listado se muestra igual, desde la base de Django."""
        import requests

        get.side_effect = requests.exceptions.ConnectionError("nadie esta")
        antes = list(Equipo.objects.order_by("id").values_list("id", flat=True))

        with self.assertLogs("inventario.resiliencia", level="ERROR") as registros:
            equipos, origen = leer_equipos()

        self.assertEqual(origen, "orm-sin-microservicios")
        # Los datos vienen del ORM, asi que el listado no queda vacio.
        self.assertEqual([e.id for e in equipos], antes)
        self.assertIn(self.laptop.id, [e.id for e in equipos])
        # Y queda asentado que los tres microservicios fallaron.
        self.assertIn("3 microservicios", "\n".join(registros.output))
        self.assertEqual(get.call_count, 3)

    @mock.patch("inventario.resiliencia.requests.get")
    def test_avanza_si_el_servicio_devuelve_json_invalido(self, get):
        """Un 200 con cuerpo que no es JSON es un fallo, no una lista vacia."""
        respuesta = mock.Mock()
        respuesta.status_code = 200
        respuesta.json.side_effect = ValueError("no es json")
        respuesta.text = "<html>error del proxy</html>"
        get.side_effect = [respuesta, respuesta_falsa(cuerpo={"equipos": []})]

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "java")
        self.assertEqual(equipos, [])

    @mock.patch("inventario.resiliencia.requests.get")
    def test_avanza_si_falta_la_clave_equipos(self, get):
        """Un JSON bien formado pero con otra forma tambien es un fallo."""
        get.side_effect = [
            respuesta_falsa(cuerpo={"otra_cosa": []}),
            respuesta_falsa(cuerpo={"equipos": [fila(1, "Desde Java")]}),
        ]

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "java")
        self.assertEqual([e.nombre for e in equipos], ["Desde Java"])

    @mock.patch("inventario.resiliencia.requests.get")
    def test_el_equipo_del_microservicio_hereda_el_tipo_legible(self, get):
        """`tipo` llega como clave; el template pide la etiqueta con
        get_tipo_display(), asi que el objeto tiene que saber convertirla.

        Sin esto, la vistaeria bien pero la tabla del listado mostraria "laptop" en
        vez de "Laptop", o peor, reventaria al llamar get_tipo_display().
        """
        get.return_value = respuesta_falsa(
            cuerpo={"equipos": [fila(1, "Notebook", tipo="proyector")]}
        )

        equipos, origen = leer_equipos()

        self.assertEqual(equipos[0].tipo, "proyector")
        self.assertEqual(equipos[0].get_tipo_display(), "Proyector")

    @mock.patch("inventario.resiliencia.requests.get")
    def test_el_id_llega_como_numero_y_no_como_texto(self, get):
        """Un id numerico se castea a int.

        Si se dejara pasar como texto, el context traeria ids mezclados y el orden
        del listado seria alfabetico ("10" antes que "2").
        """
        get.return_value = respuesta_falsa(cuerpo={"equipos": [fila(7, "Notebook")]})

        equipos, origen = leer_equipos()

        self.assertIsInstance(equipos[0].id, int)
        self.assertEqual(equipos[0].id, 7)

    @mock.patch("inventario.resiliencia.requests.get")
    def test_usa_el_timeout_configurado(self, get):
        """Cada intento tiene que tener el timeout corto de settings, no el de por
        defecto de requests (que es indefinido)."""
        get.return_value = respuesta_falsa(cuerpo={"equipos": []})

        with self.settings(TIMEOUT_MICROSERVICIOS=3):
            leer_equipos()

        self.assertEqual(get.call_args.kwargs["timeout"], 3)


class BotonesDeGuardadoTests(TestCase):
    """Los tres botones de `crear_equipo`: Python (ORM), Java y PHP."""

    def setUp(self):
        self.url = reverse("inventario:crear_equipo")
        self.datos = {"nombre": "Notebook Sinamesa", "tipo": "laptop"}
        # La migracion 0002_seed_equipos deja equipos en la base, asi que los
        # tests se apoyan en la cantidad RELATIVA (un delta) y no en un conteo
        # absoluto: si el seed cambia, estos tests siguen valiendo.
        self.cantidad_inicial = Equipo.objects.count()

    def test_el_formulario_tiene_los_tres_botones(self):
        """Sin JavaScript: los tres botones se distinguen por name/value."""
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode()
        for metodo in ("python", "java", "php"):
            self.assertIn(f'name="metodo" value="{metodo}"', html)

    def test_guardar_con_python_usa_el_orm(self):
        """El boton por defecto es el comportamiento de siempre."""
        with mock.patch("inventario.servicios_equipos.requests.post") as post:
            respuesta = self.client.post(self.url, {**self.datos, "metodo": "python"})

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Equipo.objects.count(), self.cantidad_inicial + 1)
        self.assertTrue(Equipo.objects.filter(nombre="Notebook Sinamesa").exists())
        # Y no se llamo a ningun microservicio.
        post.assert_not_called()

    @mock.patch("inventario.servicios_equipos.requests.post")
    def test_guardar_con_java_manda_el_post_al_microservicio_java(self, post):
        post.return_value = respuesta_falsa(
            status_code=201, cuerpo={"equipo": fila(1, "Notebook Sinamesa")}
        )

        respuesta = self.client.post(self.url, {**self.datos, "metodo": "java"})

        self.assertEqual(respuesta.status_code, 302)
        # Ido a la URL de Java y no a la de otro.
        self.assertEqual(post.call_args.args[0], settings.JAVA_SERVICE_URL + "/equipos")
        self.assertEqual(post.call_args.kwargs["json"]["nombre"], "Notebook Sinamesa")
        self.assertEqual(post.call_args.kwargs["json"]["tipo"], "laptop")

    @mock.patch("inventario.servicios_equipos.requests.post")
    def test_guardar_con_php_manda_el_post_al_microservicio_php(self, post):
        post.return_value = respuesta_falsa(
            status_code=201, cuerpo={"equipo": fila(1, "Notebook Sinamesa")}
        )

        respuesta = self.client.post(self.url, {**self.datos, "metodo": "php"})

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(post.call_args.args[0], settings.PHP_SERVICE_URL + "/equipos")

    @mock.patch("inventario.servicios_equipos.requests.post")
    def test_las_urls_de_java_y_php_no_se_confunden(self, post):
        """Que no se mezclen las URLs: es el error mas facil de cometer."""
        post.return_value = respuesta_falsa(
            status_code=201, cuerpo={"equipo": fila(1, "x")}
        )

        self.client.post(self.url, {**self.datos, "metodo": "php"})
        url_php = post.call_args.args[0]
        self.client.post(self.url, {**self.datos, "metodo": "java"})
        url_java = post.call_args.args[0]

        self.assertEqual(url_php, settings.PHP_SERVICE_URL + "/equipos")
        self.assertEqual(url_java, settings.JAVA_SERVICE_URL + "/equipos")
        self.assertNotEqual(url_php, url_java)

    @mock.patch("inventario.servicios_equipos.requests.post")
    def test_si_el_microservicio_cae_no_se_rompe_el_formulario(self, post):
        """Con el servicio caido se vuelve a mostrar el formulario con el error.

        Lo importante es que NO se redirected (no se perdio nada en silencio) y que
        el formulario sigue armado con lo que escribio el usuario.
        """
        import requests

        post.side_effect = requests.exceptions.ConnectionError("java caido")

        respuesta = self.client.post(self.url, {**self.datos, "metodo": "java"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo conectar")
        # No se guardo nada en el ORM: la escritura la hacia el servicio.
        self.assertEqual(Equipo.objects.count(), self.cantidad_inicial)

    @mock.patch("inventario.servicios_equipos.requests.post")
    def test_un_metodo_desconocido_cae_en_python(self, post):
        """Si llega un valor raro, se guarda con el ORM en vez de romper nada."""
        respuesta = self.client.post(self.url, {**self.datos, "metodo": "inventado"})

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Equipo.objects.count(), self.cantidad_inicial + 1)
        post.assert_not_called()

    def test_el_formulario_invalido_no_manda_nada_al_microservicio(self):
        """Se valida con el mismo form de Django antes de llamar al servicio, asi
        que un `tipo` invalido no llega a la base por la puerta de atrás."""
        with mock.patch("inventario.servicios_equipos.requests.post") as post:
            respuesta = self.client.post(
                self.url, {"nombre": "Notebook", "tipo": "avion", "metodo": "java"}
            )

        self.assertEqual(respuesta.status_code, 200)
        post.assert_not_called()
        self.assertEqual(Equipo.objects.count(), self.cantidad_inicial)


class GuardarEnMicroservicioTests(TestCase):
    """La funcion de escritura, probada directa (sin pasar por la vista)."""

    @mock.patch("inventario.servicios_equipos.requests.post")
    def test_java_devuelve_el_equipo_creado(self, post):
        post.return_value = respuesta_falsa(
            status_code=201, cuerpo={"equipo": fila(9, "Notebook")}
        )

        creado = guardar_equipo_en_microservicio(
            "java", {"nombre": "Notebook", "tipo": "laptop", "disponible": True}
        )

        self.assertEqual(creado["id"], 9)

    def test_un_servicio_invalido_es_error_de_programacion(self):
        """No es un caso de negocio: es un valor que no deberia llegar."""
        with self.assertRaises(ValueError):
            guardar_equipo_en_microservicio("cobol", {})


@override_settings(NODE_SERVICE_URL="", JAVA_SERVICE_URL="", PHP_SERVICE_URL="")
class CadenaVaciaTests(TestCase):
    """Si no hay ninguna URL configurada, se cae al ORM sin intentar ni fallar."""

    @mock.patch("inventario.resiliencia.requests.get")
    def test_cae_al_orm_sin_ninguna_url_configurada(self, get):
        # Sin URLs configuradas se lee la base: la lista tiene que traer lo mismo
        # que el ORM (que ya viene con los equipos de la migracion 0002).
        esperado = list(Equipo.objects.order_by("id").values_list("id", flat=True))

        equipos, origen = leer_equipos()

        self.assertEqual(origen, "orm-sin-microservicios")
        self.assertEqual([e.id for e in equipos], esperado)
        get.assert_not_called()
