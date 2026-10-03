# Gestion de Equipos (Django + Microservicio FastAPI + Supabase)

Aplicacion web para llevar el **inventario de equipos tecnologicos** (laptops,
proyectores, tablets, camaras), controlar los **prestamos** (quien tiene cada
equipo y cuando debe devolverse) y consultar el **historial de mantenimientos**
de cada equipo.

## Problematica

En una oficina no hay un control claro de que equipos tecnologicos estan
prestados, a quien, ni cuando deben devolverse. Ademas, la informacion de
mantenimientos vive en otro sistema/base de datos y no es visible desde la
herramienta de inventario. Esto genera perdidas, duplicados y falta de
trazabilidad.

## Solucion

Una aplicacion Django con tres modulos y **cinco** microservicios:

- **inventario**: catalogo de equipos (nombre, tipo y disponibilidad) y consulta
  del historial de mantenimientos de cada equipo.
- **prestamos**: registro de prestamos con estado (activo/devuelto) y fechas.
- **chatbot**: asistente virtual que responde preguntas sobre el inventario y
  los prestamos usando la API de Gemini.
- **microservicio** (FastAPI): API de solo lectura que expone los
  mantenimientos almacenados en PostgreSQL (Supabase).
- **microservicios de equipos** (Node, Java y PHP): tres CRUD REST independientes
  que comparten la **misma** tabla `equipo` de PostgreSQL que usa Django. Ver
  [Microservicios de equipos](#microservicios-de-equipos).

Al prestar un equipo se marca como **no disponible** y se crea el registro de
prestamo. Al devolver se marca el prestamo como devuelto, se guarda la fecha de
devolucion y el equipo vuelve a estar **disponible**.

## Arquitectura

### Inventario y mantenimientos

```
+-------------------+        HTTP (requests)        +----------------------+
|   Django (web)    |  --------------------------->  |  Microservicio       |
|   inventario +    |   GET /mantenimientos/{id}     |  FastAPI (Python)    |
|   prestamos       |  <---------------------------  |  Render              |
|   PostgreSQL      |            JSON                +----------+-----------+
+-------------------+                                           |
                                                                 | psycopg2
                                                                 v
                                                      +----------------------+
                                                      |  PostgreSQL (Supabase)|
                                                      |  tabla mantenimientos |
                                                      +----------------------+
```

### Microservicios de equipos

```
                         GET /equipos   (se prueban en orden,
                         +--------------+ se cae al siguiente si el
                         |              | anterior falla)
                         v              |
+---------+  1. primero  +--------------+ 2. +---------+ 3. +---------+
|  Node   | <---------- |              | ----> |  Java   | --> |   PHP   |
| :8082   |             |   Django     |      |  :8081  |     |  :8083  |
+---------+             |  /inventario |      +---------+     +---------+
                        +--------------+
                              |  |
                POST/PUT/DELETE|  | GET /api/equipos/ y /api/prestamos/
                              v  v          (intactos, los usa el chatbot)
                        +-------------+
                        | PostgreSQL  |
                        | tabla       |
                        | "equipo"    |
                        +-------------+

Si los TRES estan caidos, Django responde igual con su propio ORM.
```

- Los tres microservicios escriben en la **misma** tabla `equipo`, asi que los
  cambios se ven al instante en Django y en los otros dos.
- Cada uno se puede levantar y apagar por separado: la vista de listado nunca
  se rompe.
- El listado muestra de donde salieron los datos (`node`, `java`, `php` o
  `orm-sin-microservicios`).

El patron usado en las vistas es **vista -> modelo -> context -> template**: la
vista consulta el modelo, arma un diccionario `context` explicito y lo envia al
template con `render()`; los templates solo leen del context.

## Chatbot (Gemini)

El modulo `chatbot` agrega un asistente que responde preguntas en lenguaje
natural sobre el inventario y los prestamos ("quien tiene el proyector",
"cuanto se ha gastado en mantenimiento de la laptop Dell").

**Como accede a los datos: function calling, no prompt stuffing.** El modelo no
recibe los datos en el prompt; recibe la *declaracion* de cuatro herramientas y
el propio Django decide que consultar:

| Herramienta | Consulta |
| --- | --- |
| `consultar_equipos(tipo, disponible)` | Catalogo de equipos, con filtro opcional |
| `consultar_equipo(equipo_id)` | Detalle de un equipo y a quien esta prestado |
| `consultar_prestamos(estado, persona)` | Prestamos con persona y fechas |
| `consultar_mantenimientos(equipo_id)` | Historial y costo total, via microservicio |

Esto evita dos problemas: el modelo no alucina totales (el `total_gastado` lo
calcula Python con `sum(...)`, igual que en `inventario/views.py`) y el
microservicio de mantenimientos solo se consulta cuando la pregunta lo amerita.

> **Ojo con el formato de las herramientas.** La Interactions API usa el formato
> **plano** `{"type": "function", "name": ..., "description": ...,
> "parameters": ...}`. No es el formato anidado de la API legacy
> `generateContent` (`{"type": "function", "function": {...}}`), que devuelve
> `400 Missing name in function tool`. Es el error mas comun al migrar.

**El chatbot es de solo lectura.** No registra prestamos ni devoluciones.

### Estructura

```
gestion_equipos/chatbot/
├── models.py      # Conversacion y Mensaje (historial persistido)
├── views.py       # pagina del chat + endpoint JSON
├── gemini.py      # UNICO modulo que importa google.genai
├── tools.py       # declaraciones de herramientas + su implementacion Django
├── services.py    # loop de function calling y reconstruccion del historial
└── templates/chatbot/chat.html
```

`gemini.py` aisla el SDK a proposito: cambiar de modelo, de API o de proveedor
se hace en un solo archivo.

### Como se guarda la conversacion

Se usa la **Interactions API** de Gemini con `store=False`: el estado vive en la
base de datos, no en el servidor de Google. Como la API exige reenviar los
steps del modelo tal cual (contienen *thought signatures*), el modelo `Mensaje`
guarda el campo `pasos` con el JSON crudo. Ese campo no es opcional: sin el, el
segundo turno con function calling falla.

### Costo

Funciona con el **plan gratuito** de la API de Gemini. `GEMINI_MODEL` esta
configurado en un modelo Flash, que es el que permite el plan gratuito. El
function calling no se cobra aparte: solo se paga por tokens, y con 6 equipos
el consumo es minimo.

En el plan gratuito Google puede usar el contenido enviado para mejorar sus
productos. Si esto llegara a production con datos de personas reales, habria que
pasar al plan de pago.

## Microservicios de equipos

Tres CRUD REST que comparten la tabla `equipo`. Cada uno tiene su carpeta, su
README y su Dockerfile.

| Servicio | Puerto | Stack | Documentacion |
| --- | --- | --- | --- |
| `microservicio-node/` | 8082 | Node + Express + `pg` | `/api-docs` (Swagger UI) |
| `microservicio-java/` | 8081 | Spring Boot + JPA | `/swagger-ui.html` |
| `microservicio-php/` | 8083 | PHP puro + PDO | `/docs` (Swagger UI estatico) |

Los tres exponen los mismos endpoints:

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| GET | `/` | Salud del servicio (JSON) |
| GET | `/equipos` | Lista todos los equipos |
| GET | `/equipos/{id}` | Un equipo por id |
| POST | `/equipos` | Crea un equipo |
| PUT | `/equipos/{id}` | Actualiza un equipo |
| DELETE | `/equipos/{id}` | Elimina un equipo |

### Levantar cada uno

```bash
# Node
cd microservicio-node
npm install
npm start

# Java
cd microservicio-java
mvn spring-boot:run

# PHP (Docker)
docker build -t microservicio-php microservicio-php
docker run -p 8083:8083 -e DB_HOST=host.docker.internal -e DB_USER=gestion -e DB_PASSWORD=... microservicio-php
```

Los tres leen la conexion del entorno (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`); Node tambien acepta `DATABASE_URL`.

### Como decide Django de donde leer

`inventario/resiliencia.py` prueba `NODE_SERVICE_URL`, `JAVA_SERVICE_URL` y
`PHP_SERVICE_URL` en ese orden. Pasa al siguiente cuando hay timeout, se rechaza
la conexon o la respuesta es `>= 500`. Si los tres fallan, usa su propio ORM.

El guardado tiene tres botones en `/equipo/nuevo/`, y cada uno escribe por un
camino distinto: **Guardar con Python** por el ORM de Django, **Guardar con
Java** por `POST` a Java y **Guardar con PHP** por `POST` a PHP.

> **Trampa de PDO:** los marcadores de consulta son `?` y **no** `$1`. PDO trae su
> propio parser y solo entiende `?` y `:nombre`; si se escriben `$1`, PostgreSQL
> los recibe como parametros que nadie envio y todas las columnas llegan en NULL.

## Requisitos

- Python 3.10 o superior
- Git (opcional)

## Crear entorno virtual e instalar dependencias

```bash
# Windows
python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

```bash
# Linux / macOS
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

## Configurar variables de entorno

Copia el archivo `.env.example` a `.env` y ajusta los valores:

```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

```env
# Base de datos del inventario (Django + los 3 microservicios de equipos)
DB_ENGINE=postgres
DB_NAME=gestion_equipos
DB_USER=gestion
DB_PASSWORD=tu_password
DB_HOST=localhost
DB_PORT=5432

# Cadena de microservicios del listado, en orden de preferencia
NODE_SERVICE_URL=http://localhost:8082
JAVA_SERVICE_URL=http://localhost:8081
PHP_SERVICE_URL=http://localhost:8083
TIMEOUT_MICROSERVICIOS=3

# Microservicio de mantenimientos y chatbot
MICROSERVICIO_URL=http://localhost:8001
DATABASE_URL=postgresql://usuario:password@host:5432/postgres?sslmode=require
GEMINI_API_KEY=tu_clave_de_gemini
GEMINI_MODEL=gemini-3.6-flash
```

- `DB_ENGINE`: con `postgres` usa PostgreSQL; si no se define, Django sigue con
  SQLite (`db.sqlite3`) y el proyecto funciona como venia.
- `DB_*`: los microservicios de equipos usan las **mismas** variables, para que
  los cuatro apunten a la misma base de datos.
- `NODE_SERVICE_URL`, `JAVA_SERVICE_URL`, `PHP_SERVICE_URL`: orden en que se
  consulta el listado. Si alguno esta caido, se pasa al siguiente sin avisar.
- `TIMEOUT_MICROSERVICIOS`: segundos de espera por servicio antes de continuar.
- `MICROSERVICIO_URL`: URL base del microservicio de mantenimientos. En local es
  `http://localhost:8001`; en produccion sera la URL de Render.
- `DATABASE_URL`: cadena de conexion a PostgreSQL/Supabase (la usa el
  microservicio de mantenimientos, no Django).
- `GEMINI_API_KEY`: clave de la API de Gemini, se obtiene gratis en
  <https://aistudio.google.com/apikey>. Sin ella, el resto de la aplicacion
  funciona igual y el chatbot muestra un aviso de configuracion.
- `GEMINI_MODEL`: modelo del chatbot. La oferta de modelos de Gemini cambia
  seguido, por eso es configurable. Debe ser un modelo Flash para usar el plan
  gratuito.

La API key solo se usa en el servidor Django: nunca se envia al navegador.

El archivo `.env` esta en `.gitignore` y no debe subirse al repositorio.

## Migrar la base de datos

```bash
python manage.py migrate
```

Este paso crea las tablas y ademas carga **6 equipos de ejemplo** mediante una
migracion de datos.

## Crear superusuario (admin)

```bash
python manage.py createsuperuser
```

Tambien se puede crear uno de forma no interactiva:

```bash
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin','admin@example.com','admin1234')"
```

## Correr todo localmente

Necesitas **dos terminales**: una para el microservicio y otra para Django.

**Terminal 1 - microservicio FastAPI (puerto 8001):**

```bash
cd microservicio
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

**Terminal 2 - Django (puerto 8000):**

```bash
venv\Scripts\activate          # Windows
python manage.py migrate
python manage.py runserver
```

> Si no levantas el microservicio, la pagina de mantenimientos mostrara un
> mensaje de error controlado indicando que no se pudo conectar.

## URLs de Django

| URL | Descripcion |
| --- | --- |
| `/` | Listado de equipos (inventario), servido por la cadena de microservicios |
| `/equipo/nuevo/` | Formulario con los tres botones de guardado |
| `/equipo/<id>/` | Detalle de un equipo |
| `/api/equipos/` | API JSON de equipos (la consume el chatbot) |
| `/api/prestamos/` | API JSON de prestamos (la consume el chatbot) |
| `/equipo/<id>/mantenimientos/` | Historial de mantenimientos del equipo |
| `/equipo/<id>/prestar/` | Formulario para prestar un equipo |
| `/prestamos/` | Listado de prestamos activos |
| `/prestamo/<id>/devolver/` | Registrar devolucion de un prestamo |
| `/chatbot/` | Chat con el asistente (Gemini) |
| `/chatbot/api/mensaje/` | Endpoint JSON del chatbot (solo POST) |
| `/admin/` | Panel de administracion de Django |

## Endpoints del microservicio

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| GET | `/` | Mensaje de salud del servicio (JSON) |
| GET | `/mantenimientos` | Lista todos los mantenimientos |
| GET | `/mantenimientos/{equipo_id}` | Mantenimientos de un equipo |
| GET | `/docs` | Documentacion interactiva (Swagger UI) |

## Desplegar el microservicio en Render

1. Crea un **Web Service** en [Render](https://render.com) conectado al repositorio.
2. Configura:

   | Campo | Valor |
   | --- | --- |
   | **Root Directory** | `microservicio` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
   | **Environment Variable** | `DATABASE_URL` = cadena de conexion de Supabase |

3. Una vez desplegado, copia la URL publica del servicio y usala como
   `MICROSERVICIO_URL` en el entorno donde corra Django.

## Estructura del proyecto

```
ProyectoDjangoProblematica/
├── gestion_equipos/            # Proyecto Django
│   ├── manage.py
│   ├── gestion_equipos/        # Configuracion (settings, urls)
│   ├── inventario/             # App de inventario y mantenimientos
│   │   ├── resiliencia.py       # Cadena Node -> Java -> PHP -> ORM
│   │   ├── servicios_equipos.py # Escritura via Java / PHP
│   │   └── test_resiliencia.py # Tests de la cadena y los 3 botones
│   ├── prestamos/              # App de prestamos
│   ├── chatbot/                # App del asistente con Gemini
│   ├── static/                 # Assets (JavaScript del chatbot)
│   └── templates/              # Template base compartido
├── microservicio/              # Microservicio FastAPI de mantenimientos
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── microservicio-node/         # CRUD de equipos en Node (8082)
├── microservicio-java/         # CRUD de equipos en Spring Boot (8081)
├── microservicio-php/          # CRUD de equipos en PHP puro (8083)
├── requirements.txt            # Dependencias de Django
├── .env.example                # Ejemplo de variables de entorno
└── README.md
```

## Pruebas

```bash
python manage.py test
```

Los tests no dependen de los microservicios: `test_resiliencia.py` simula las
caidas con `unittest.mock`, asi que la suite pasa aunque los tres esten apagados.
