<?php
/**
 * Microservicio de equipos en PHP, SIN framework.
 *
 * No hay Laravel, ni Slim, ni Symfony: el enrutado se resuelve a mano leyendo
 * $_SERVER['REQUEST_METHOD'] y la ruta de $_SERVER['REQUEST_URI']. Asi el servicio
 * corre con el servidor embebido sin instalar nada:
 *
 *     php -S 0.0.0.0:8083 index.php
 *
 * (El servidor embebido de PHP es single-threaded: atiende una peticion por vez.
 * Para produccion se pondria php-fpm o Apache, pero para desarrollo y para que
 * Django lo use en la cadena de respaldo es suficiente.)
 *
 * Es el TERCERO de la cadena de lectura de Django: si Node y Java no responden,
 * Django cae aca y, si tampoco, usa su propio ORM.
 *
 * La tabla `equipo` es la MISMA que usan Django (por su ORM) y los microservicios
 * Java (por JPA) y Node (por pg). La conexion sale de variables de entorno y no
 * esta escrita en este archivo.
 */

// ---------------------------------------------------------------------------
// Los warnings de PHP van al log (stderr) y NUNCA a la salida estandar. Si uno se
// imprimiera en el cuerpo de la respuesta, pasaria adelante del JSON y Django haria
// `respuesta.json()` sobre "<br /><b>Warning</b>: ...{...}", reventando con un error
// de parseo en vez de caer limpiamente al siguiente microservicio de la cadena.
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('error_log', 'php://stderr');
// Configuracion
// ---------------------------------------------------------------------------

/**
 * Devuelve el valor de una variable de entorno.
 *
 * Se usa getenv() en vez de $_ENV/$_SERVER porque getenv() lee el entorno real del
 * proceso, que es lo que inyecta Docker (-e PORT=...) o un hosting de
 * contenedores. $_ENV solo se puebla si alguien la copio a mano.
 */
function entorno(string $nombre, ?string $porDefecto = null): ?string
{
    $valor = getenv($nombre);
    if ($valor === false || $valor === '') {
        return $porDefecto;
    }
    return $valor;
}

// La configuracion vive DENTRO de una funcion a proposito: si estas variables
// estuvieran sueltas a nivel de archivo, las funciones de abajo no las verian. En
// PHP el ambito de una funcion son sus propias variables mas las globales
// declaradas con `global`, y un script servido por `php -S` no las expone solo.
// El fallo de dejarlo asi es confuso: las funciones leen cadena vacia, el DSN
// queda "host=;port=;dbname=" y la conexion falla con un error de host inexplicable.
function config(): array
{
    static $config = null;
    if ($config !== null) {
        return $config;
    }

    $config = [
        // La clave no tiene default a proposito: si falta, Postgres rechaza la
        // autenticacion y el error lo dice claro.
        'db_host' => entorno('DB_HOST', 'localhost'),
        'db_port' => entorno('DB_PORT', '5432'),
        'db_name' => entorno('DB_NAME', 'gestion_equipos'),
        'db_user' => entorno('DB_USER', 'gestion'),
        'db_password' => entorno('DB_PASSWORD', ''),
        'tabla' => entorno('EQUIPOS_TABLE', 'equipo'),
    ];

    return $config;
}

/**
 * Connection de PDO, reutilizada durante el pedido.
 *
 * El servidor embebido crea el proceso una vez y resuelve many peticiones
 * (PHP dibuja el proceso, includes y ejecuta). Por eso la connection se guarda en
 * una variable estatica y no se abre en cada ruta.
 *
 * @return PDO
 */
function conexion(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }

    // El DSN se arma con los valores del entorno. No se interpola nada que venga
    // del usuario: es connection config, no entrada de formulario.
    $config = config();
    $dsn = sprintf('pgsql:host=%s;port=%s;dbname=%s', $config['db_host'], $config['db_port'], $config['db_name']);

    try {
        $pdo = new PDO($dsn, $config['db_user'], $config['db_password'], [
            // Errores como excepciones: por defecto PDOagrieta en silencio si
            // alguien se olvida de mirar errorInfo(), y un INSERT fallido
            // pareceria un exito.
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            // Consulta preparada nativa del driver, que ademas permite reutilizar
            // la consulta en el servidor (prepared statements).
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
    } catch (PDOException $e) {
        // 503 y no 500: es el estado >= 500 que hace que la vista de Django pase
        // al siguiente recurso de la cadena (en este caso, su propio ORM).
        responder(503, [
            'error' => 'No se pudo conectar con la base de datos.',
            'detalle' => $e->getMessage(),
        ]);
        // responder() con codigo >= 400 corta la ejecucion con exit, asi que
        // desde aca no se sigue.
    }

    return $pdo;
}

/**
 * Envia una respuesta JSON y termina el pedido.
 *
 * @param int $codigo
 * @param array $cuerpo
 * @return never
 */
function responder(int $codigo, array $cuerpo): void
{
    http_response_code($codigo);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($cuerpo, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

/**
 * Lee el cuerpo JSON de la peticion y lo devuelve como arreglo.
 *
 * @return array
 */
function cuerpoJson(): array
{
    $crudo = file_get_contents('php://input');
    if ($crudo === false || trim($crudo) === '') {
        return [];
    }
    $datos = json_decode($crudo, true);
    // Si no es un objeto/array JSON, se trata como cuerpo vacio y la validacion
    // de abajo es la que produce el error legible.
    return is_array($datos) ? $datos : [];
}

/**
 * Cuenta caracteres de un texto.
 *
 * `mb_strlen` cuenta caracteres UTF-8 (que es lo que mide el max_length=100 de
 * Django: "Notebook Ñ" son 9 caracteres, no 10 bytes), pero necesita la extension
 * mbstring, que no esta en todas las instalaciones de PHP. Si falta, se cae a
 * strlen(), que cuenta bytes: en el peor caso es mas estricto y rechaza antes un
 * nombre valido con many acentos, lo cual es preferible a aceptarlo y que lo
 * rechace la base.
 */
function longitud(string $texto): int
{
    return function_exists('mb_strlen') ? mb_strlen($texto, 'UTF-8') : strlen($texto);
}

/**
 * Normaliza y valida el cuerpo de un POST/PUT.
 *
 * Mismo contrato que los otros dos microservicios: devuelve los valores ya
 * convertidos al tipo de la columna o un mensaje de error.
 *
 * @param array $cuerpo
 * @return array{datos: array<string,mixed>, error: ?string}
 */
function validarEquipo(array $cuerpo): array
{
    $errores = [];

    $nombre = isset($cuerpo['nombre']) ? trim((string) $cuerpo['nombre']) : '';
    if ($nombre === '') {
        $errores[] = 'El campo "nombre" es obligatorio.';
    } elseif (longitud($nombre) > 100) {
        // 100 es el max_length del CharField de Django.
        $errores[] = 'El campo "nombre" no puede superar los 100 caracteres.';
    }

    $tiposValidos = ['laptop', 'proyector', 'tablet', 'camara'];
    $tipo = isset($cuerpo['tipo']) ? strtolower(trim((string) $cuerpo['tipo'])) : '';
    if ($tipo === '') {
        $errores[] = 'El campo "tipo" es obligatorio.';
    } elseif (!in_array($tipo, $tiposValidos, true)) {
        $errores[] = 'El campo "tipo" debe ser uno de: ' . implode(', ', $tiposValidos) . '.';
    }

    // `disponible` es NOT NULL con default TRUE. Se aceptan los strings que
    // mandan los formularios HTML (el checkbox de Django viaja como "on"), igual
    // que en el microservicio Node.
    $disponible = true;
    if (isset($cuerpo['disponible']) && $cuerpo['disponible'] !== '') {
        if (is_bool($cuerpo['disponible'])) {
            $disponible = $cuerpo['disponible'];
        } else {
            $texto = strtolower(trim((string) $cuerpo['disponible']));
            if (in_array($texto, ['true', '1', 'on', 'si', 'yes'], true)) {
                $disponible = true;
            } elseif (in_array($texto, ['false', '0', 'off', 'no'], true)) {
                $disponible = false;
            } else {
                $errores[] = 'El campo "disponible" debe ser true o false.';
            }
        }
    }

    if ($errores !== []) {
        return ['datos' => [], 'error' => implode(' ', $errores)];
    }

    return [
        'datos' => [
            'nombre' => $nombre,
            'tipo' => $tipo,
            'disponible' => $disponible,
        ],
        'error' => null,
    ];
}

/**
 * Devuelve un equipo en el formato que comparten los tres microservicios.
 *
 * `id` se castea a int a proposito: PDO devuelve los enteros de PostgreSQL como
 * string (porque bigint puede no entrar en un int de PHP), y el JSON tiene que
 * traer `id` como numero para ser compatible con el de Java y Node y para que
 * Django arme sus objetos Equipo con el tipo correcto.
 *
 * @param array $fila
 * @return array<string,mixed>
 */
function aEquipo(array $fila): array
{
    return [
        'id' => (int) $fila['id'],
        'nombre' => $fila['nombre'],
        // Clave, no etiqueta legible: Django traduce con get_tipo_display().
        'tipo' => $fila['tipo'],
        'disponible' => (bool) $fila['disponible'],
    ];
}

/**
 * Empaqueta las filas de un SELECT en la forma {equipo: {...}} o {equipos: [...]}.
 *
 * @param array $filas
 * @return array<string,mixed>
 */
function empaquetar(array $filas): array
{
    if (count($filas) === 1) {
        return ['equipo' => aEquipo($filas[0])];
    }
    return ['equipos' => array_map('aEquipo', $filas)];
}

// ---------------------------------------------------------------------------
// Rutas de solo lectura
// ---------------------------------------------------------------------------

/**
 * GET /docs -> documentacion Swagger UI.
 *
 * Este servicio NO genera la especificacion solo (no hay anotaciones ni framework
 * que las lea), asi que la especificacion esta escrita a mano en openapi.yaml y
 * Swagger UI se sirve desde public/ apuntando a ese archivo. Un unico YAML para
 * los tres clientes (los que quieren HTML y los que quieren el YAML).
 */
function servirDocs(): void
{
    header('Content-Type: text/html; charset=utf-8');
    readfile(__DIR__ . '/public/index.html');
}

/**
 * GET /openapi.yaml -> la especificacion cruda, para clientes que no son browser.
 */
function servirEspecificacion(): void
{
    header('Content-Type: application/yaml; charset=utf-8');
    readfile(__DIR__ . '/openapi.yaml');
}

// ---------------------------------------------------------------------------
// Enrutado
// ---------------------------------------------------------------------------

$ruta = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$metodo = strtoupper($_SERVER['REQUEST_METHOD'] ?? 'GET');

// Se saca la barra final para que /equipos y /equipos/ sean la misma ruta.
$ruta = rtrim($ruta, '/');
if ($ruta === '') {
    $ruta = '/';
}

// GET /docs y GET /openapi.yaml se resuelven antes que el CRUD.
if ($metodo === 'GET' && $ruta === '/docs') {
    servirDocs();
    exit;
}
if ($metodo === 'GET' && $ruta === '/openapi.yaml') {
    servirEspecificacion();
    exit;
}

// GET / -> mensaje de salud.
if ($metodo === 'GET' && $ruta === '/') {
    responder(200, [
        'servicio' => 'microservicio-equipos-php',
        'lenguaje' => 'PHP',
        'estado' => 'ok',
        'endpoints' => ['/equipos', '/docs'],
    ]);
}

// GET /equipos -> lista todos los equipos.
if ($metodo === 'GET' && $ruta === '/equipos') {
    try {
        $filas = conexion()
            ->query(sprintf('SELECT id, nombre, tipo, disponible FROM %s ORDER BY id', config()['tabla']))
            ->fetchAll(PDO::FETCH_ASSOC);
        responder(200, ['equipos' => array_map('aEquipo', $filas)]);
    } catch (PDOException $e) {
        responder(503, [
            'error' => 'No se pudo consultar la base de datos.',
            'detalle' => $e->getMessage(),
        ]);
    }
}

// POST /equipos -> inserta un equipo.
if ($metodo === 'POST' && $ruta === '/equipos') {
    $validacion = validarEquipo(cuerpoJson());
    if ($validacion['error'] !== null) {
        responder(400, ['error' => $validacion['error']]);
    }
    $datos = $validacion['datos'];

    try {
        // La consulta va PREPARADA: los valores viajan como parametros y nunca
        // concatenados en el texto, asi que un `nombre` con comillas no puede romper
        // la consulta ni inyectar SQL.
        //
        // Los marcadores son `?` y NO los `$1` de PostgreSQL. PDO tiene su propio
        // parser de marcadores (solo entiende `?` y `:nombre`) y es independiente
        // del driver: si se escriben `$1`, PDO los reenvia tal cual al servidor,
        // que los interpreta como parametros que nadie envio, y cada columna del
        // INSERT llega en NULL. El error que sale es un "null value in column"
        // que no dice nada de marcadores, por eso conviene saberlo.
        $sentencia = conexion()->prepare(sprintf(
            'INSERT INTO %s (nombre, tipo, disponible) VALUES (?, ?, ?) RETURNING id, nombre, tipo, disponible',
            config()['tabla']
        ));
        $sentencia->execute([$datos['nombre'], $datos['tipo'], $datos['disponible'] ? 'true' : 'false']);

        $fila = $sentencia->fetch(PDO::FETCH_ASSOC);
        http_response_code(201);
        header('Content-Type: application/json; charset=utf-8');
        header('Location: /equipos/' . $fila['id']);
        echo json_encode(['equipo' => aEquipo($fila)], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        exit;
    } catch (PDOException $e) {
        responder(503, [
            'error' => 'No se pudo completar la operacion sobre la base de datos.',
            'detalle' => $e->getMessage(),
        ]);
    }
}

// Las tres rutas que llevan un id: PUT /equipos/{id}, DELETE /equipos/{id} y
// GET /equipos/{id}. Se resuelve el id con una expresion regular sobre la ruta.
if (preg_match('#^/equipos/(\d+)$#', $ruta, $coincidencias) === 1) {
    $id = (int) $coincidencias[1];

    // GET /equipos/{id} -> un equipo por id.
    if ($metodo === 'GET') {
        try {
            $sentencia = conexion()->prepare(sprintf(
                'SELECT id, nombre, tipo, disponible FROM %s WHERE id = ?',
                config()['tabla']
            ));
            $sentencia->execute([$id]);
            $fila = $sentencia->fetch(PDO::FETCH_ASSOC);
            if ($fila === false) {
                responder(404, ['error' => 'No existe un equipo con id ' . $id . '.']);
            }
            responder(200, ['equipo' => aEquipo($fila)]);
        } catch (PDOException $e) {
            responder(503, [
                'error' => 'No se pudo consultar la base de datos.',
                'detalle' => $e->getMessage(),
            ]);
        }
    }

    // PUT /equipos/{id} -> actualiza un equipo existente.
    if ($metodo === 'PUT') {
        $validacion = validarEquipo(cuerpoJson());
        if ($validacion['error'] !== null) {
            responder(400, ['error' => $validacion['error']]);
        }
        $datos = $validacion['datos'];

        try {
            $sentencia = conexion()->prepare(sprintf(
                'UPDATE %s SET nombre = ?, tipo = ?, disponible = ? WHERE id = ?
                 RETURNING id, nombre, tipo, disponible',
                config()['tabla']
            ));
            $sentencia->execute([
                $datos['nombre'],
                $datos['tipo'],
                $datos['disponible'] ? 'true' : 'false',
                $id,
            ]);
            $fila = $sentencia->fetch(PDO::FETCH_ASSOC);
            // RETURNING vacio significa que el WHERE no matcheo: el id no existe.
            // No es un error de la base sino un 404 del recurso.
            if ($fila === false) {
                responder(404, ['error' => 'No existe un equipo con id ' . $id . '.']);
            }
            responder(200, ['equipo' => aEquipo($fila)]);
        } catch (PDOException $e) {
            responder(503, [
                'error' => 'No se pudo completar la operacion sobre la base de datos.',
                'detalle' => $e->getMessage(),
            ]);
        }
    }

    // DELETE /equipos/{id} -> borra un equipo.
    if ($metodo === 'DELETE') {
        try {
            $sentencia = conexion()->prepare(sprintf('DELETE FROM %s WHERE id = ? RETURNING id', config()['tabla']));
            $sentencia->execute([$id]);
            $fila = $sentencia->fetch(PDO::FETCH_ASSOC);
            if ($fila === false) {
                responder(404, ['error' => 'No existe un equipo con id ' . $id . '.']);
            }
            responder(200, ['eliminado' => (int) $fila['id']]);
        } catch (PDOException $e) {
            responder(503, [
                'error' => 'No se pudo completar la operacion sobre la base de datos.',
                'detalle' => $e->getMessage(),
            ]);
        }
    }
}

// Cualquier otra combinacion de metodo y ruta.
// Si la ruta existe pero se pidio con otro verbo, se responde 405 con la cabecera
// Allow, que es lo que dice el protocolo HTTP. Si la ruta no existe, 404.
$rutaDeEquipos = $ruta === '/equipos' || preg_match('#^/equipos/\d+$#', $ruta) === 1;
if ($rutaDeEquipos) {
    $conId = preg_match('#^/equipos/\d+$#', $ruta) === 1;
    header('Allow: ' . ($conId ? 'GET, PUT, DELETE' : 'GET, POST'));
    responder(405, [
        'error' => 'El metodo ' . $metodo . ' no esta permitido en ' . $ruta . '.',
    ]);
}

responder(404, ['error' => 'Ruta no encontrada: ' . $metodo . ' ' . $ruta]);
