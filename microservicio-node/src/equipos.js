/**
 * Rutas CRUD de la tabla compartida `equipo`.
 *
 * Contrato con Django: GET /equipos devuelve el mismo JSON que los otros dos
 * microservicios (Java y PHP) para que la vista de Django pueda meter el
 * resultado en el mismo context sin preguntar de donde vino.
 *
 *   `tipo` se devuelve como CLAVE (laptop, proyector, tablet, camara), no como
 *   etiqueta legible ("Laptop"). La etiqueta depende del idioma y Django la
 *   deriva sola con get_tipo_display() sobre su propio modelo; mandar las dos
 *   seria redundante y con la clave alcanza.
 */

'use strict';

const express = require('express');
const config = require('./config');
const TIPOS_VALIDOS = require('./tipos');
const { consultar } = require('./db');

const router = express.Router();

const T = config.tabla;

/**
 * Normaliza el cuerpo de un POST/PUT.
 *
 * Devuelve { datos } con los valores ya convertidos al tipo de la columna, o
 * { error } con el motivo. Se separa del handler para que el handler no tenga
 * que decidir que es un error de validacion y que es un error de base.
 */
function validarEquipo(cuerpo) {
  const errores = [];
  const datos = {};

  const nombre = (cuerpo?.nombre ?? '').toString().trim();
  if (!nombre) {
    errores.push('El campo "nombre" es obligatorio.');
  } else if (nombre.length > 100) {
    // 100 es el max_length del CharField de Django: si se pasa, el INSERT lo
    // acepta en Postgres pero Django no podria leerlo nunca.
    errores.push('El campo "nombre" no puede superar los 100 caracteres.');
  } else {
    datos.nombre = nombre;
  }

  const tipo = (cuerpo?.tipo ?? '').toString().trim().toLowerCase();
  if (!tipo) {
    errores.push('El campo "tipo" es obligatorio.');
  } else if (!TIPOS_VALIDOS.includes(tipo)) {
    errores.push(`El campo "tipo" debe ser uno de: ${TIPOS_VALIDOS.join(', ')}.`);
  } else {
    datos.tipo = tipo;
  }

  // `disponible` es booleano NOT NULL con default TRUE. Si no viene, se usa TRUE
  // (el mismo default que el modelo Django). Acepta los strings que mandan los
  // formularios HTML, porque el checkbox de Django viaja como "on" o no viaja.
  if (
    cuerpo?.disponible === undefined ||
    cuerpo?.disponible === null ||
    cuerpo?.disponible === ''
  ) {
    datos.disponible = true;
  } else if (typeof cuerpo.disponible === 'boolean') {
    datos.disponible = cuerpo.disponible;
  } else {
    const normalizado = cuerpo.disponible.toString().trim().toLowerCase();
    if (['true', '1', 'on', 'si', 'yes'].includes(normalizado)) {
      datos.disponible = true;
    } else if (['false', '0', 'off', 'no'].includes(normalizado)) {
      datos.disponible = false;
    } else {
      errores.push('El campo "disponible" debe ser true o false.');
    }
  }

  if (errores.length > 0) {
    return { error: errores.join(' ') };
  }
  return { datos };
}

/**
 * @openapi
 * /equipos:
 *   get:
 *     tags: [equipos]
 *     summary: Lista todos los equipos
 *     description: >
 *       Devuelve el inventario completo. Es el endpoint que el proyecto Django
 *       consulta PRIMERO; si falla, Django cae al microservicio Java.
 *     responses:
 *       200:
 *         description: Lista de equipos.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 equipos:
 *                   type: array
 *                   items:
 *                     $ref: '#/components/schemas/Equipo'
 *       500:
 *         description: No se pudo consultar la base de datos.
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.get('/equipos', async (req, res, next) => {
  try {
    const filas = await consultar(`SELECT id, nombre, tipo, disponible FROM ${T} ORDER BY id`);
    res.json({ equipos: filas });
  } catch (err) {
    next(err);
  }
});

/**
 * @openapi
 * /equipos/{id}:
 *   get:
 *     tags: [equipos]
 *     summary: Devuelve un equipo por id
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema: { type: integer }
 *     responses:
 *       200:
 *         description: El equipo pedido.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 equipo:
 *                   $ref: '#/components/schemas/Equipo'
 *       404:
 *         description: No existe un equipo con ese id.
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.get('/equipos/:id', async (req, res, next) => {
  const id = Number.parseInt(req.params.id, 10);
  if (!Number.isInteger(id)) {
    return res.status(400).json({ error: 'El id debe ser un numero entero.' });
  }
  try {
    const filas = await consultar(
      `SELECT id, nombre, tipo, disponible FROM ${T} WHERE id = $1`,
      [id],
    );
    if (filas.length === 0) {
      return res.status(404).json({ error: `No existe un equipo con id ${id}.` });
    }
    res.json({ equipo: filas[0] });
  } catch (err) {
    next(err);
  }
});

/**
 * @openapi
 * /equipos:
 *   post:
 *     tags: [equipos]
 *     summary: Inserta un equipo
 *     description: >
 *       Django usa este endpoint solo para leer (GET); las escrituras del
 *       formulario van al microservicio Java o al de PHP. Se expone igual para
 *       poder cargar datos o probar el servicio con curl.
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/Equipo'
 *     responses:
 *       201:
 *         description: Equipo creado, con el id generado por la base.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 equipo:
 *                   $ref: '#/components/schemas/Equipo'
 *       400:
 *         description: Faltan campos o `tipo` no es valido.
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.post('/equipos', async (req, res, next) => {
  const { datos, error } = validarEquipo(req.body);
  if (error) {
    return res.status(400).json({ error });
  }
  try {
    const filas = await consultar(
      `INSERT INTO ${T} (nombre, tipo, disponible) VALUES ($1, $2, $3)
       RETURNING id, nombre, tipo, disponible`,
      [datos.nombre, datos.tipo, datos.disponible],
    );
    // 201 Created + Location es lo que corresponde a un POST que creo un
    // recurso; el cliente (o Django) ya tiene el id para usarlo despues.
    res
      .status(201)
      .location(`/equipos/${filas[0].id}`)
      .json({ equipo: filas[0] });
  } catch (err) {
    next(err);
  }
});

/**
 * @openapi
 * /equipos/{id}:
 *   put:
 *     tags: [equipos]
 *     summary: Actualiza un equipo existente
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema: { type: integer }
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             $ref: '#/components/schemas/Equipo'
 *     responses:
 *       200:
 *         description: Equipo actualizado.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 equipo:
 *                   $ref: '#/components/schemas/Equipo'
 *       400:
 *         description: Faltan campos o `tipo` no es valido.
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 *       404:
 *         description: No existe un equipo con ese id.
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.put('/equipos/:id', async (req, res, next) => {
  const id = Number.parseInt(req.params.id, 10);
  if (!Number.isInteger(id)) {
    return res.status(400).json({ error: 'El id debe ser un numero entero.' });
  }
  const { datos, error } = validarEquipo(req.body);
  if (error) {
    return res.status(400).json({ error });
  }
  try {
    const filas = await consultar(
      `UPDATE ${T} SET nombre = $1, tipo = $2, disponible = $3
       WHERE id = $4
       RETURNING id, nombre, tipo, disponible`,
      [datos.nombre, datos.tipo, datos.disponible, id],
    );
    if (filas.length === 0) {
      // RETURNING vacio significa que el WHERE no matcheo: el id no existe. No es
      // un error de la base sino un 404 del recurso.
      return res.status(404).json({ error: `No existe un equipo con id ${id}.` });
    }
    res.json({ equipo: filas[0] });
  } catch (err) {
    next(err);
  }
});

/**
 * @openapi
 * /equipos/{id}:
 *   delete:
 *     tags: [equipos]
 *     summary: Elimina un equipo
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema: { type: integer }
 *     responses:
 *       200:
 *         description: Equipo eliminado.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 eliminado: { type: integer }
 *       404:
 *         description: No existe un equipo con ese id.
 *         content:
 *           application/json:
 *             schema:
 *               $ref: '#/components/schemas/Error'
 */
router.delete('/equipos/:id', async (req, res, next) => {
  const id = Number.parseInt(req.params.id, 10);
  if (!Number.isInteger(id)) {
    return res.status(400).json({ error: 'El id debe ser un numero entero.' });
  }
  try {
    const filas = await consultar(`DELETE FROM ${T} WHERE id = $1 RETURNING id`, [id]);
    if (filas.length === 0) {
      return res.status(404).json({ error: `No existe un equipo con id ${id}.` });
    }
    res.json({ eliminado: id });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
