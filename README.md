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

Una aplicacion Django con dos modulos y un microservicio:

- **inventario**: catalogo de equipos (nombre, tipo y disponibilidad) y consulta
  del historial de mantenimientos de cada equipo.
- **prestamos**: registro de prestamos con estado (activo/devuelto) y fechas.
- **microservicio** (FastAPI): API de solo lectura que expone los
  mantenimientos almacenados en PostgreSQL (Supabase).

Al prestar un equipo se marca como **no disponible** y se crea el registro de
prestamo. Al devolver se marca el prestamo como devuelto, se guarda la fecha de
devolucion y el equipo vuelve a estar **disponible**.

## Arquitectura

```
+-------------------+        HTTP (requests)        +----------------------+
|   Django (web)    |  --------------------------->  |  Microservicio       |
|   inventario +    |   GET /mantenimientos/{id}     |  FastAPI (Python)    |
|   prestamos       |  <---------------------------  |  Render              |
|   SQLite (local)  |            JSON                +----------+-----------+
+-------------------+                                           |
                                                                | psycopg2
                                                                v
                                                     +----------------------+
                                                     |  PostgreSQL (Supabase)|
                                                     |  tabla mantenimientos |
                                                     +----------------------+
```

- **Django** usa SQLite para equipos y prestamos, y consume el microservicio por
  HTTP para los mantenimientos.
- **Microservicio FastAPI** se conecta a Supabase con `DATABASE_URL` y expone
  los mantenimientos en JSON con CORS abierto.
- La URL del microservicio se configura en Django con `MICROSERVICIO_URL`.

El patron usado en las vistas es **vista -> modelo -> context -> template**: la
vista consulta el modelo, arma un diccionario `context` explicito y lo envia al
template con `render()`; los templates solo leen del context.

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
MICROSERVICIO_URL=http://localhost:8001
DATABASE_URL=postgresql://usuario:password@host:5432/postgres?sslmode=require
```

- `MICROSERVICIO_URL`: URL base del microservicio de mantenimientos. En local es
  `http://localhost:8001`; en produccion sera la URL de Render.
- `DATABASE_URL`: cadena de conexion a PostgreSQL/Supabase (la usa el
  microservicio, no Django).

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
| `/` | Listado de equipos (inventario) |
| `/equipo/<id>/` | Detalle de un equipo |
| `/equipo/<id>/mantenimientos/` | Historial de mantenimientos del equipo |
| `/equipo/<id>/prestar/` | Formulario para prestar un equipo |
| `/prestamos/` | Listado de prestamos activos |
| `/prestamo/<id>/devolver/` | Registrar devolucion de un prestamo |
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
│   ├── prestamos/              # App de prestamos
│   └── templates/              # Template base compartido
├── microservicio/              # Microservicio FastAPI (independiente)
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── requirements.txt            # Dependencias de Django
├── .env.example                # Ejemplo de variables de entorno
└── README.md
```
