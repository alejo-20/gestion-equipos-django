/**
 * Documentacion de la API con swagger-jsdoc.
 *
 * A diferencia de Spring Boot o FastAPI, Node no genera la especificacion solo:
 * hay que escribirla. Se escribe como JSDoc pegado a cada ruta, asi que la
 * documentacion y el handler viven en el mismo archivo y no se desincronizan.
 * Swagger UI se sirve en /api-docs.
 */

'use strict';

const swaggerJSDoc = require('swagger-jsdoc');
const TIPOS_VALIDOS = require('./tipos');

const definicion = {
  openapi: '3.0.3',
  info: {
    title: 'Microservicio de Equipos (Node.js)',
    version: '1.0.0',
    description:
      'CRUD de la tabla `equipo` compartida con Django y con los microservicios ' +
      'Java y PHP. Es el primero que consulta el proyecto Django para leer el ' +
      'inventario.',
  },
  servers: [{ url: '/', description: 'Este servicio' }],
  tags: [{ name: 'equipos', description: 'Operaciones sobre la tabla `equipo`' }],
  components: {
    schemas: {
      Equipo: {
        type: 'object',
        properties: {
          id: { type: 'integer', example: 7 },
          nombre: { type: 'string', maxLength: 100, example: 'Notebook Lenovo ThinkPad' },
          tipo: { type: 'string', enum: TIPOS_VALIDOS, example: 'laptop' },
          disponible: { type: 'boolean', example: true },
        },
      },
      Error: {
        type: 'object',
        properties: { error: { type: 'string' } },
      },
    },
  },
};

const opciones = {
  definition: definicion,
  // Solo se documentan las rutas de equipos.js: el server tiene tambien /health,
  // que es un endpoint de operativo interno y no parte de la API.
  apis: ['./src/equipos.js'],
};

const especificacion = swaggerJSDoc(opciones);

module.exports = especificacion;
