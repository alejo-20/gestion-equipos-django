/**
 * Pool de conexiones a PostgreSQL.
 *
 * Un unico pool por proceso, compartido por todas las peticiones: abrir una
 * conexion TCP + handshake de autenticacion por request es lo mas caro de la
 * operacion y con el pool se paga una sola vez.
 */

'use strict';

const { Pool, types } = require('pg');
const config = require('./config');

// Por default el driver devuelve `bigint` (OID 20, el tipo de la columna `id`,
// que Django crea como BigAutoField) como STRING, para no perder precision con
// valores por encima de 2^53. El problema es que el JSON de este servicio tiene
// que ser el MISMO que el de Java y PHP, donde `id` es un numero, y Django
// construye los objetos Equipo con ese valor: si `id` fuera "7" (texto) en vez de
// 7, el context del template queda con tipos mezclados y `orden_by` sobre el id
// ordena lexicograficamente ("10" antes que "2").
// Un id de inventario jamas llega a 2^53, asi que Number() es seguro aca.
types.setTypeParser(20, (valor) => Number(valor));

const pool = new Pool(config.db);

// Un cliente que se va sin dejar la respuesta a medias (Node se apaga, la red se
// cae) no libera el socket y el pool se queda sin conexiones disponibles hasta
// que el timeout lo revienta. Con este listener el error queda logueado.
pool.on('error', (err) => {
  console.error('[microservicio-node] error inesperado del pool de Postgres:', err.message);
});

/**
 * Ejecuta una consulta y devuelve las filas.
 *
 * Se parametrizan TODAS las consultas: los valores viajan como parametros de
 * PostgreSQL ($1, $2, ...) y nunca concatenados en el texto SQL, asi que un
 * `nombre` con comillas no puede romper la consulta ni inyectar SQL.
 *
 * @param {string} texto SQL con marcadores $1, $2...
 * @param {Array<any>} valores
 * @returns {Promise<Array<object>>}
 */
async function consultar(texto, valores = []) {
  const resultado = await pool.query(texto, valores);
  return resultado.rows;
}

module.exports = { pool, consultar };
