# Gestion de Equipos (Django)

Aplicacion web simple para llevar el **inventario de equipos tecnologicos** (laptops, proyectores, tablets, camaras) y controlar los **prestamos**: quien tiene cada equipo y cuando debe devolverse.

## Problema

En una oficina no hay un control claro de que equipos tecnologicos estan prestados, a quien, ni cuando deben devolverse. Esto genera perdidas, duplicados y falta de trazabilidad.

## Solucion

Una app Django con dos modulos:

- **inventario**: catalogo de equipos (nombre, tipo y disponibilidad).
- **prestamos**: registro de prestamos activos con estado (activo/devuelto) y fechas.

Al prestar un equipo se marca como **no disponible** y se crea el registro de prestamo. Al devolver se marca el prestamo como devuelto, se guarda la fecha de devolucion y el equipo vuelve a estar **disponible**.

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

## Migrar la base de datos

```bash
python manage.py migrate
```

Este paso crea las tablas y ademas carga **6 equipos de ejemplo** mediante una migracion de datos.

## Crear superusuario (admin)

```bash
python manage.py createsuperuser
```

Tambien se puede crear uno de forma no interactiva:

```bash
python manage.py shell -c "from django.contrib.auth.models import User; User.objects.create_superuser('admin','admin@example.com','admin1234')"
```

## Correr el servidor

```bash
python manage.py runserver
```

Acceder a:

- http://127.0.0.1:8000/ - Inventario (home)
- http://127.0.0.1:8000/prestamos/ - Prestamos activos
- http://127.0.0.1:8000/admin/ - Panel de administracion

## URLs principales

| URL | Descripcion |
| --- | --- |
| `/` | Listado de equipos (inventario) |
| `/equipo/<id>/` | Detalle de un equipo |
| `/equipo/<id>/prestar/` | Formulario para prestar un equipo |
| `/prestamos/` | Listado de prestamos activos |
| `/prestamo/<id>/devolver/` | Registrar devolucion de un prestamo |
| `/admin/` | Panel de administracion de Django |

## Estructura del proyecto

```
gestion_equipos/
├── manage.py
├── gestion_equipos/        # Configuracion del proyecto (settings, urls)
├── inventario/             # App de inventario de equipos
├── prestamos/              # App de prestamos
├── templates/              # Template base compartido
└── db.sqlite3              # Base de datos SQLite (generada con migrate)
```