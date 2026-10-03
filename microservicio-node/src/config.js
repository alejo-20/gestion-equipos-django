/**
 * Lectura de la configuracion desde variables de entorno.
 *
 * La conexion a Postgres SIEMPRE viene del entorno: aca no hay ninguna credencial
 * escrita. Se aceptan dos formatos, en este orden de prioridad:
 *
 *   1. `DATABASE_URL` (una sola cadena, el formato que ya usa el microservicio
 *      FastAPI de mantenimientos).
 *   2. Las variables sueltas `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` y
 *      `DB_PASSWORD`, que son las MISMAS que lee Django en settings.py. Usar las
 *      dos familias permite clonar un unico .env y que los cuatro participantes
 *      (Django, Java, Node y PHP) apunten a la misma base.
 */

'use strict';

require('dotenv').config();

function leerUrlDeConexion() {
  const url = (process.env.DATABASE_URL || '').trim();
  if (!url) {
    return null;
  }
  // Se acepta postgres:// y postgresql://. `pg` entiende las dos, pero se
  // normaliza a postgresql:// porque es la forma canica de la cadena.
  return url.replace(/^postgres(ql)?:\/\//, 'postgresql://');
}

const urlDeConexion = leerUrlDeConexion();

const config = {
  port: Number.parseInt(process.env.PORT || '8082', 10),

  // Defaults pensados para desarrollo local (docker run -p 5432:5432 postgres).
  // La clave NO tiene default a proposito: si falta, `pg` falla al conectar y el
  // error dice que la autenticacion fallo, que es mas util que adivinar.
  db: urlDeConexion
    ? { connectionString: urlDeConexion }
    : {
        host: process.env.DB_HOST || 'localhost',
        port: Number.parseInt(process.env.DB_PORT || '5432', 10),
        database: process.env.DB_NAME || 'gestion_equipos',
        user: process.env.DB_USER || 'gestion',
        password: process.env.DB_PASSWORD || '',
      },

  // Nombre de la tabla compartida. Es `equipo` porque Django la creo con
  // `class Meta: db_table = 'equipo'`. Se puede cambiar por entorno para no
  // tener el nombre clavado en el codigo.
  tabla: process.env.EQUIPOS_TABLE || 'equipo',

  // Maximo de conexiones del pool. Es chico a proposito: este servicio solo
  // responde consultas simples sobre una tabla de inventario.
  maxConexiones: Number.parseInt(process.env.DB_POOL_MAX || '5', 10),
};

module.exports = config;
