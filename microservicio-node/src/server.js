/**
 * Arranque del microservicio de equipos (Node.js + Express).
 *
 * Es el primero de los tres que consulta Django para leer el inventario, asi que
 * arranca y responde rapido: Express no levanta un contenedor de inyeccion de
 * dependencias ni una JVM.
 */

'use strict';

const express = require('express');
const swaggerUi = require('swagger-ui-express');

const config = require('./config');
const equipos = require('./equipos');
const { pool } = require('./db');
const especificacion = require('./openapi');

const app = express();

// El cuerpo del POST /equipos y del PUT viaja como JSON. Sin este middleware
// `req.body` seria undefined y la validacion no tendria nada que mirar.
app.use(express.json());

// El proyecto Django y Swagger UI llaman a este servicio desde OTRO origen
// (no son peticiones del mismo puerto), asi que el navegador las trata como
// cross-origin. El CORS se abre solo para este servicio interno.
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }
  return next();
});

/** GET / -> mensaje de salud. No forma parte de la API documentada. */
app.get('/', (req, res) => {
  res.json({
    servicio: 'microservicio-equipos-node',
    lenguaje: 'Node.js',
    estado: 'ok',
    endpoints: ['/equipos', '/api-docs'],
  });
});

app.use(equipos);

// Documentacion interactiva. El HTML de Swagger UI se carga del paquete
// swagger-ui-express (local, no por CDN) y la especificacion sale de swagger-jsdoc.
app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(especificacion));

/**
 * Middleware de errores, ultimo de todos.
 *
 * Sin esto un error de Postgres (tabla inexistente, caida de conexion) sale como
 * respuesta vacia con status 200 y Django lo toma por una lista valida. Aca se
 * traduce a 503 con un mensaje, que es justo el status >= 500 que hace que la
 * vista de Django pase al siguiente microservicio.
 */
app.use((err, req, res, next) => {
  console.error(`[microservicio-node] error en ${req.method} ${req.originalUrl}:`, err.message);
  res.status(503).json({
    error: 'No se pudo completar la operacion sobre la base de datos.',
    detalle: err.message,
  });
});

const servidor = app.listen(config.port, () => {
  console.log(`[microservicio-node] escuchando en http://localhost:${config.port}`);
  console.log(`[microservicio-node] documentacion en http://localhost:${config.port}/api-docs`);
});

/**
 * Apagado ordenado: al recibir SIGINT/SIGTERM (Ctrl+C, docker stop) se deja de
 * aceptar conexiones y se espera a que terminen las que estan en vuelo. Sin esto
 * un POST que ya habia swiftado la conexion puede cortar a la mitad y dejar la
 * base con la escritura a medias.
 */
function apagar(senal) {
  console.log(`[microservicio-node] ${senal} recibido, cerrando...`);
  servidor.close(async () => {
    await pool.end();
    console.log('[microservicio-node] pool de Postgres cerrado.');
    process.exit(0);
  });
}

process.on('SIGINT', () => apagar('SIGINT'));
process.on('SIGTERM', () => apagar('SIGTERM'));
