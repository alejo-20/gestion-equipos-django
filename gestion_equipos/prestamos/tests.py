from django.test import TestCase
from django.urls import reverse

from inventario.models import Equipo

from .models import Prestamo


class ApiPrestamosTests(TestCase):
    """El endpoint que consume el chatbot: publico, JSON y de solo lectura."""

    def setUp(self):
        self.equipo = Equipo.objects.create(nombre="Notebook Siamesa", tipo="laptop")
        self.activo = Prestamo.objects.create(
            equipo=self.equipo, nombre_persona="Ana Diaz"
        )
        self.devuelto = Prestamo.objects.create(
            equipo=self.equipo,
            nombre_persona="Bruno Soto",
            fecha_devolucion="2026-02-01T18:00:00Z",
            devuelto=True,
        )
        self.url = reverse("prestamos:api_prestamos")

    def test_devuelve_lista_de_prestamos_en_json(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        self.assertIn("prestamos", respuesta.json())
        self.assertEqual(len(respuesta.json()["prestamos"]), 2)

    def test_cada_prestamo_trae_los_campos_pedidos(self):
        datos = self.client.get(self.url).json()
        prestamo = next(
            p for p in datos["prestamos"] if p["id"] == self.activo.id
        )

        self.assertEqual(
            set(prestamo),
            {
                "id",
                "equipo_id",
                "equipo",
                "nombre_persona",
                "fecha_prestamo",
                "fecha_devolucion",
                "devuelto",
            },
        )
        self.assertEqual(prestamo["equipo"], "Notebook Siamesa")
        self.assertEqual(prestamo["nombre_persona"], "Ana Diaz")
        self.assertIs(prestamo["devuelto"], False)
        self.assertIsNone(prestamo["fecha_devolucion"])

    def test_las_fechas_salen_en_iso_8601(self):
        datos = self.client.get(self.url).json()
        prestamo = next(p for p in datos["prestamos"] if p["id"] == self.activo.id)

        # auto_now_add la pone Django, asi que tiene que venir ya formateada.
        self.assertRegex(prestamo["fecha_prestamo"], r"^\d{4}-\d{2}-\d{2}T")

    def test_filtra_por_estado_activo(self):
        datos = self.client.get(self.url, {"estado": "activo"}).json()

        self.assertEqual(
            [p["nombre_persona"] for p in datos["prestamos"]], ["Ana Diaz"]
        )

    def test_filtra_por_estado_devuelto(self):
        datos = self.client.get(self.url, {"estado": "devuelto"}).json()

        self.assertEqual(
            [p["nombre_persona"] for p in datos["prestamos"]], ["Bruno Soto"]
        )

    def test_sin_estado_devuelve_todos(self):
        datos = self.client.get(self.url).json()

        self.assertEqual(len(datos["prestamos"]), 2)

    def test_filtra_por_persona_con_busqueda_parcial(self):
        datos = self.client.get(self.url, {"persona": "diaz"}).json()

        self.assertEqual(
            [p["nombre_persona"] for p in datos["prestamos"]], ["Ana Diaz"]
        )

    def test_estado_invalido_no_falla(self):
        respuesta = self.client.get(self.url, {"estado": "inventado"})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.json()["prestamos"]), 2)

    def test_es_de_solo_lectura(self):
        for metodo in ("post", "put", "delete", "patch"):
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(self.url)
                self.assertEqual(respuesta.status_code, 405)

    def test_no_crea_prestamos_con_un_post(self):
        antes = Prestamo.objects.count()
        self.client.post(self.url, {"equipo": self.equipo.id, "nombre_persona": "Intruso"})
        self.assertEqual(Prestamo.objects.count(), antes)


class SincronizacionDisponibleTests(TestCase):
    """`Equipo.disponible` tiene que quedar acorde a los prestamos en el CRUD.

    Antes solo `devolver_prestamo` actualizaba ese flag, asi que crear, editar o
    borrar un prestamo desde el formulario dejaba el equipo "disponible" y el
    chatbot contestaba que nadie lo tenia. Estos tests fijan el comportamiento
    que evita esa desincronizacion.
    """

    def setUp(self):
        self.proyector = Equipo.objects.create(nombre="Proyector Epson EB-X50", tipo="proyector")
        self.laptop = Equipo.objects.create(nombre="Notebook Lenovo ThinkPad", tipo="laptop")
        self.url_crear = reverse("prestamos:crear_prestamo")

    def _refrescar(self, equipo):
        """Vuelve a leer el equipo de la base para ver el valor guardado."""
        return Equipo.objects.get(pk=equipo.pk)

    def _crear(self, equipo, nombre="Ana Diaz", devuelto=False):
        """Crea un prestamo por el formulario (igual que lo haria el usuario)."""
        datos = {"equipo": equipo.pk, "nombre_persona": nombre}
        if devuelto:
            datos["devuelto"] = "on"
            datos["fecha_devolucion"] = "2026-02-01T18:00"
        self.client.post(self.url_crear, datos)
        return Prestamo.objects.get(nombre_persona=nombre)

    def _editar(self, prestamo, devuelto=None, **campos):
        """Edita un prestamo por el formulario.

        El checkbox `devuelto` se manda solo si se pide: si se omite, el form lo
        guarda en False, que es como funciona el checkbox en el navegador.
        """
        datos = {
            "equipo": prestamo.equipo_id,
            "nombre_persona": prestamo.nombre_persona,
        }
        if devuelto is True:
            datos["devuelto"] = "on"
        datos.update(campos)
        return self.client.post(
            reverse("prestamos:editar_prestamo", args=[prestamo.pk]), datos
        )

    def _eliminar(self, prestamo):
        return self.client.post(
            reverse("prestamos:eliminar_prestamo", args=[prestamo.pk])
        )

    def test_crear_prestamo_marca_el_equipo_como_no_disponible(self):
        """El bug: crear el prestamo por el formulario dejaba el flag en True."""
        respuesta = self.client.post(
            self.url_crear, {"equipo": self.proyector.id, "nombre_persona": "Ana Diaz"}
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Prestamo.objects.count(), 1)
        self.assertFalse(self._refrescar(self.proyector).disponible)

    def test_crear_prestamo_ya_devuelto_deja_el_equipo_disponible(self):
        """El formulario expone `devuelto`: si nace devuelto, el equipo queda libre."""
        self.client.post(
            self.url_crear,
            {
                "equipo": self.proyector.id,
                "nombre_persona": "Ana Diaz",
                "devuelto": "on",
                "fecha_devolucion": "2026-02-01T18:00",
            },
        )

        self.assertEqual(Prestamo.objects.count(), 1)
        self.assertTrue(self._refrescar(self.proyector).disponible)

    def test_el_prestamo_creado_aparece_de_inmediato_en_la_api(self):
        """El endpoint que consume el chatbot tiene que reflejar el POST al instante."""
        self.client.post(
            self.url_crear, {"equipo": self.proyector.id, "nombre_persona": "Ana Diaz"}
        )

        prestamos = self.client.get(
            reverse("prestamos:api_prestamos"), {"estado": "activo"}
        ).json()["prestamos"]

        self.assertEqual(len(prestamos), 1)
        self.assertEqual(prestamos[0]["equipo"], "Proyector Epson EB-X50")
        self.assertEqual(prestamos[0]["nombre_persona"], "Ana Diaz")
        self.assertIs(prestamos[0]["devuelto"], False)

        # Y el equipo figura como no disponible en /api/equipos/.
        equipos = self.client.get(
            reverse("inventario:api_equipos"), {"disponible": "false"}
        ).json()["equipos"]
        self.assertIn(self.proyector.id, [e["id"] for e in equipos])

    def test_editar_marcar_devuelto_libera_el_equipo(self):
        prestamo = self._crear(self.proyector)

        self._editar(prestamo, devuelto=True)

        self.assertTrue(self._refrescar(self.proyector).disponible)

    def test_editar_a_devuelto_no_libera_si_hay_otro_prestamo_activo(self):
        """Dos prestamos activos del mismo equipo: al devolver uno sigue ocupado."""
        prestamo = self._crear(self.proyector, nombre="Ana Diaz")
        self._crear(self.proyector, nombre="Bruno Soto")

        self._editar(prestamo, devuelto=True)

        self.assertFalse(self._refrescar(self.proyector).disponible)

    def test_editar_volver_a_activo_ocupa_el_equipo(self):
        prestamo = self._crear(self.proyector, devuelto=True)

        # Sin checkbox "devuelto" el form lo guarda en False.
        self._editar(prestamo)

        self.assertFalse(self._refrescar(self.proyector).disponible)

    def test_editar_cambio_de_equipo_ocupa_el_nuevo_y_libera_el_anterior(self):
        prestamo = self._crear(self.proyector)

        self._editar(prestamo, equipo=self.laptop.pk)

        self.assertFalse(self._refrescar(self.laptop).disponible)
        self.assertTrue(self._refrescar(self.proyector).disponible)

    def test_editar_cambio_de_equipo_no_libera_el_anterior_si_tiene_otro_activo(self):
        prestamo = self._crear(self.proyector, nombre="Ana Diaz")
        self._crear(self.proyector, nombre="Bruno Soto")

        self._editar(prestamo, equipo=self.laptop.pk)

        self.assertFalse(self._refrescar(self.proyector).disponible)
        self.assertFalse(self._refrescar(self.laptop).disponible)

    def test_editar_prestamo_devuelto_a_otro_equipo_deja_libre_el_anterior(self):
        prestamo = self._crear(self.proyector, devuelto=True)
        # Se parte del flag en False para que el test no pase por casualidad: el
        # prestamo ya fue devuelto, asi que el proyector quedo desincronizado.
        self.proyector.disponible = False
        self.proyector.save()

        self._editar(prestamo, equipo=self.laptop.pk, devuelto=True)

        self.assertTrue(self._refrescar(self.proyector).disponible)
        self.assertTrue(self._refrescar(self.laptop).disponible)

    def test_eliminar_prestamo_activo_libera_el_equipo(self):
        prestamo = self._crear(self.proyector)

        self._eliminar(prestamo)

        self.assertEqual(Prestamo.objects.count(), 0)
        self.assertTrue(self._refrescar(self.proyector).disponible)

    def test_eliminar_prestamo_activo_no_libera_si_queda_otro_activo(self):
        prestamo = self._crear(self.proyector, nombre="Ana Diaz")
        self._crear(self.proyector, nombre="Bruno Soto")

        self._eliminar(prestamo)

        self.assertEqual(Prestamo.objects.count(), 1)
        self.assertFalse(self._refrescar(self.proyector).disponible)

    def test_devolver_prestamo_sigue_liberando_el_equipo(self):
        """La vista que ya existia no se toco: esto la cubre contra regressions."""
        prestamo = self._crear(self.proyector)

        self.client.post(reverse("prestamos:devolver_prestamo", args=[prestamo.pk]))

        prestamo.refresh_from_db()
        self.assertTrue(prestamo.devuelto)
        self.assertIsNotNone(prestamo.fecha_devolucion)
        self.assertTrue(self._refrescar(self.proyector).disponible)

    def test_prestar_equipo_sigue_marcando_el_equipo_como_no_disponible(self):
        antes = Prestamo.objects.count()

        respuesta = self.client.post(
            reverse("prestamos:prestar_equipo", args=[self.proyector.id]),
            {"nombre_persona": "Carla Ruiz"},
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Prestamo.objects.count(), antes + 1)
        self.assertFalse(self._refrescar(self.proyector).disponible)

