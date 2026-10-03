# Microservicio de Equipos (PHP sin framework)

CRUD de la tabla `equipo` **compartida** con el proyecto Django y con los
microservicios Java y Node. Es el **tercero** que consulta Django para leer el
inventario: primero Node, despues Java, y este ultimo antes de recurrir al propio
ORM de Django.

**No usa ningun framework**: el enrutado se resuelve a mano por metodo HTTP y
ruta en `index.php`, y la base se accede con `PDO` + driver `pdo_pgsql`.

## Variables de entorno

`PORT` (default `8083`), `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
(las mismas que leen Django, Node y Java) y `EQUIPOS_TABLE` (default `equipo`).
Ninguna credencial esta escrita en el codigo. Ver `.env.example`.

## Correr localmente

```bash
php -S 0.0.0.0:8083 index.php
```

Queda en `http://localhost:8083`, documentacion en `/docs` y especificacion
cruda en `/openapi.yaml`.

## Endpoints

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| GET | `/equipos` | Lista todos los equipos. |
| GET | `/equipos/{id}` | Un equipo por id (404 si no existe). |
| POST | `/equipos` | Inserta y devuelve el id generado (201). |
| PUT | `/equipos/{id}` | Actualiza (404 si no existe). |
| DELETE | `/equipos/{id}` | Elimina (404 si no existe). |

Un verbo no permitido en una ruta existente responde **405** con la cabecera
`Allow`; una ruta desconocida, **404**.

## Documentacion

Como no hay anotaciones que generen la especificacion, `openapi.yaml` esta
escrito a mano y es la fuente de verdad de la API. Swagger UI se sirve como
archivo estatico (`public/index.html`) apuntando a ese YAML, y lo carga desde un
CDN con la version fijada: sin salida a internet la pagina avisa que no pudo
cargar y el YAML sigue disponible en `/openapi.yaml`.

## Docker

```bash
docker build -t microservicio-php .
docker run -p 8083:8083 -e DB_HOST=host.docker.internal -e DB_USER=gestion -e DB_PASSWORD=... microservicio-php
```

> Este servicio usa el servidor embebido (`php -S`), que es monoproceso y de un
> solo hilo: atiende una peticion a la vez y no tiene opcion de workers. Para
> concurrencia real habria que usar php-fpm con nginx por delante, o correr varias
> replicas del contenedor.
