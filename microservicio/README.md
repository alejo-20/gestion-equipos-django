# Microservicio de Mantenimientos (FastAPI)

Microservicio independiente del proyecto Django que expone, en formato JSON,
los mantenimientos de equipos almacenados en una base de datos PostgreSQL en
la nube (**Supabase**).

## Tecnologias

- **FastAPI** como framework web.
- **Uvicorn** como servidor ASGI.
- **psycopg2-binary** como driver de PostgreSQL.
- **python-dotenv** para leer variables de entorno locales desde `.env`.

## Requisitos

- Python 3.10 o superior.
- Una base de datos PostgreSQL con la tabla `mantenimientos`:

| Columna | Tipo |
| --- | --- |
| `id` | serial PRIMARY KEY |
| `equipo_id` | integer |
| `descripcion` | text |
| `tecnico` | varchar |
| `fecha` | date |
| `costo` | numeric |

## Variable de entorno

El servicio **nunca** hardcodea credenciales. Lee la cadena de conexion de la
variable de entorno `DATABASE_URL`:

```
DATABASE_URL=postgresql://usuario:password@host:5432/postgres?sslmode=require
```

Puedes crear un archivo `.env` (no se sube a Git) a partir de `.env.example`.

## Correr localmente

```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Linux / macOS
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Luego:

```bash
uvicorn main:app --reload --port 8001
```

El servicio queda en `http://127.0.0.1:8001`.

## Endpoints

| Metodo | Ruta | Descripcion |
| --- | --- | --- |
| GET | `/` | Mensaje de salud del servicio (JSON). |
| GET | `/mantenimientos` | Lista todos los mantenimientos. |
| GET | `/mantenimientos/{equipo_id}` | Lista los mantenimientos de un equipo. |

La documentacion interactiva queda disponible en `/docs`.

## Desplegar en Render

1. Crea un nuevo **Web Service** en [Render](https://render.com) y conecta el
   repositorio de GitHub de este proyecto.
2. Configura los campos asi:

   | Campo | Valor |
   | --- | --- |
   | **Root Directory** | `microservicio` |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
   | **Environment Variable** | `DATABASE_URL` = tu cadena de conexion de Supabase |

3. Crea el servicio. Render asignara una URL publica, por ejemplo
   `https://mi-microservicio.onrender.com`.
4. Copia esa URL y usala en el proyecto Django como `MICROSERVICIO_URL` (por
   ejemplo en el `.env` de Django o en las variables de entorno de Render).

> Nota: en el plan free de Render el servicio se "duerme" tras un tiempo de
> inactividad, por eso la app Django usa un `timeout` de 60 segundos.

## Estructura

```
microservicio/
├── main.py            # Aplicacion FastAPI y endpoints
├── requirements.txt   # Dependencias del microservicio
├── .env.example       # Ejemplo de variables de entorno
└── README.md          # Este archivo
```
