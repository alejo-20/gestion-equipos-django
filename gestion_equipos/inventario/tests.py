from django.test import TestCase
from django.urls import reverse

from .models import Equipo


class ApiEquiposTests(TestCase):
    """El endpoint que consume el chatbot: publico, JSON y de solo lectura."""

    def setUp(self):
        # La migracion 0002_seed_equipos deja equipos en la base, asi que los
        # tests se apoyan en los equipos creados aqui y no en conteos absolutos.
        self.laptop = Equipo.objects.create(nombre="Notebook Siamesa", tipo="laptop")
        self.proyector = Equipo.objects.create(
            nombre="Proyectorukan", tipo="proyector", disponible=False
        )
        self.url = reverse("inventario:api_equipos")

    def test_devuelve_lista_de_equipos_en_json(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        datos = respuesta.json()
        self.assertIn("equipos", datos)
        nombres = [e["nombre"] for e in datos["equipos"]]
        self.assertIn("Notebook Siamesa", nombres)
        self.assertIn("Proyectorukan", nombres)

    def test_cada_equipo_trae_los_cuatro_campos(self):
        datos = self.client.get(self.url).json()
        equipo = next(e for e in datos["equipos"] if e["nombre"] == "Notebook Siamesa")

        self.assertEqual(
            set(equipo), {"id", "nombre", "tipo", "disponible"}
        )
        self.assertEqual(equipo["id"], self.laptop.id)
        # La etiqueta legible, no la clave del choices.
        self.assertEqual(equipo["tipo"], "Laptop")
        self.assertIs(equipo["disponible"], True)

    def test_filtra_por_tipo(self):
        datos = self.client.get(self.url, {"tipo": "proyector"}).json()

        self.assertTrue(all(e["tipo"] == "Proyector" for e in datos["equipos"]))
        self.assertIn("Proyectorukan", [e["nombre"] for e in datos["equipos"]])
        self.assertNotIn("Notebook Siamesa", [e["nombre"] for e in datos["equipos"]])

    def test_filtra_por_disponible(self):
        datos = self.client.get(self.url, {"disponible": "false"}).json()

        self.assertIn("Proyectorukan", [e["nombre"] for e in datos["equipos"]])
        self.assertNotIn("Notebook Siamesa", [e["nombre"] for e in datos["equipos"]])

    def test_filtros_combinados(self):
        # El proyector de este test no esta disponible, asi que tiene que quedar
        # afuera aunque coincida el tipo.
        nombres = [
            e["nombre"]
            for e in self.client.get(
                self.url, {"tipo": "proyector", "disponible": "true"}
            ).json()["equipos"]
        ]

        self.assertNotIn("Proyectorukan", nombres)

    def test_tipo_inexistente_devuelve_lista_vacia_y_no_error(self):
        respuesta = self.client.get(self.url, {"tipo": "avion"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"equipos": []})

    def test_es_de_solo_lectura(self):
        for metodo in ("post", "put", "delete", "patch"):
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(self.url)
                self.assertEqual(respuesta.status_code, 405)

    def test_no_crea_equipos_con_un_post(self):
        antes = Equipo.objects.count()
        self.client.post(self.url, {"nombre": "Intruso", "tipo": "laptop"})
        self.assertEqual(Equipo.objects.count(), antes)
