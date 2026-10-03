# Microservicio de Equipos (Node.js + Express)

CRUD de la tabla `equipo` **compartida** con el proyecto Django y con los
microservicios Java y PHP. Es el **primero** que consulta Django para leer el
inventario: si este esta caido, Django pasa al de Java, despues al de PHP y como
ultimo recurso usa su propio ORM.

## Variables de entorno

La conexion **nunca** esta hardcodeada. Se acepta cualquiera de las dos formas:

| Forma | Variables |
| --- | --- |
| Cadena unica (tiene prioridad si se define) | `DATABASE_URL=postgresql://user:clave@host:5432/bd` |
| Variables sueltas (las mismas que lee Django) | `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` |

Others: `PORT` (default `8082`), `EQUIPOS_TABLE` (default `equipo`) y
`DB_POOL_MAX` (default `5`). Copia `.env.example` a `.env` y completalo.

## Correr localmente

```bash
npm install
# .env con DB_PASSWORD=... (o DATABASE_URL=...)
npm start            # http://localhost:8082  |  docs en /api-docs
```

## Endpoints

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| GET | `/equipos` | Lista todos los equipos. |
| GET | `/equipos/{id}` | Un equipo por id (404 si no existe). |
| POST | `/equipos` | Inserta y devuelve el id generado (201). |
| PUT | `/equipos/{id}` | Actualiza (404 si no existe). |
| DELETE | `/equipos/{id}` | Elimina (404 si no existe). |

La documentacion interactiva (Swagger UI + especificacion generada con
`swagger-jsdoc` desde los JSDoc de `src/equipos.js`) queda en `/api-docs`.

## Notas de contrato

- `tipo` se devuelve como **clave** (`laptop`, `proyector`, `tablet`, `camara`),
  no como etiqueta legible: Django arma el modelo `Equipo` con ese valor y
  traduce solo con `get_tipo_display()`.
- `id` se devuelve como **numero**. El driver `pg` devuelve `bigint` como string,
  asi que `src/db.js` registra un type parser para el OID 20; sin eso el JSON
  seria incompatible con el de Java/PHP.
- Todas las consultas van **parametrizadas** (`$1`, `$2`), nunca concatenadas.
- Los errores de base se responden con **503**, que es el estado que hace que la
  vista de Django avance al siguiente microservicio de la cadena.

## Docker

```bash
docker build -t microservicio-node .
docker run -p 8082:8082 -e DB_HOST=host.docker.internal -e DB_USER=gestion -e DB_PASSWORD=... microservicio-node
```
