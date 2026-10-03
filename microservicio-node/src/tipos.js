/**
 * Opciones validas de `equipo.tipo`.
 *
 * Son las mismas cuatro del `TIPOS` del modelo Equipo de Django. Se declaran
 * aca para que este microservicio se pueda deployar y validar por su cuenta,
 * sin depender de que este Django levantado, y para que los tres microservicios
 * (Java, Node y PHP) compartan exactamente el mismo dominio.
 */

'use strict';

module.exports = ['laptop', 'proyector', 'tablet', 'camara'];
