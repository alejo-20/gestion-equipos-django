# Microservicio de Equipos (Java + Spring Boot)

CRUD de la tabla `equipo` **compartida** con el proyecto Django y con los
microservicios Node y PHP. Es el **segundo** que consulta Django para leer el
inventario: si Node no responde, Django pasa a este y, si tampoco, al de PHP.

Usa **Spring Data JPA** sobre PostgreSQL y publica la documentacion OpenAPI con
**springdoc-openapi** en `/swagger-ui.html`.

## Variables de entorno

La conexion **nunca** esta hardcodeada; sale de `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER` y `DB_PASSWORD` (las mismas que lee Django, para compartir un unico
`.env`), mas `PORT` (default `8081`) y `DB_POOL_MAX`. Ver `.env.example`.

Spring las lee del entorno directamente, asi que en local alcanza con:

```bash
export DB_PASSWORD=gestion_dev     # Linux / macOS
$env:DB_PASSWORD="gestion_dev"    # PowerShell
```

## Correr localmente

```bash
mvn spring-boot:run
# o bien, para no depender de Maven instalado:
mvn -DskipTests package && java -jar target/microservicio-java-1.0.0.jar
```

Queda en `http://localhost:8081`, documentacion en `/swagger-ui.html` y
especificacion en `/v3/api-docs`.

## Endpoints

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| GET | `/equipos` | Lista todos los equipos. |
| GET | `/equipos/{id}` | Un equipo por id (404 si no existe). |
| POST | `/equipos` | Inserta y devuelve el id generado (201). |
| PUT | `/equipos/{id}` | Actualiza (404 si no existe). |
| DELETE | `/equipos/{id}` | Elimina (404 si no existe). |

## Notas

- `ddl-auto: validate`: la tabla la crea Django con sus migraciones. Este servicio
  solo verifica que el mapeo coincida y **no** crea ni altera nada. Ese chequeo ya
  vale: con `BigInteger` en el `id` el arranque falla con `found [int8], but
  expecting [numeric(38,0)]`, porque la columna `id` es `bigint`.
- `@GeneratedValue(IDENTITY)`: delega en el `identity` de la columna y devuelve el
  id en el INSERT. Sin eso, todo POST falla con `Identifier of entity must be
  manually assigned`.
- Los errores de base se responden con **503**, el estado `>= 500` que hace que la
  vista de Django avance al siguiente recurso de la cadena.
- `tipo` viaja como clave (`laptop`), no como etiqueta legible; Django la deriva
  con `get_tipo_display()`.

## Docker

```bash
docker build -t microservicio-java .
docker run -p 8081:8081 -e DB_HOST=host.docker.internal -e DB_USER=gestion -e DB_PASSWORD=... microservicio-java
```
