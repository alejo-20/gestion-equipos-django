"""Microservicio de mantenimientos de equipos.

Expone los mantenimientos almacenados en PostgreSQL (Supabase) como JSON.
Es independiente del proyecto Django y se conecta usando DATABASE_URL.
"""

import os
from datetime import date, datetime
from decimal import Decimal

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

# La URL de conexion SIEMPRE se lee de la variable de entorno DATABASE_URL.
# Nunca se hardcodean credenciales en el codigo.
DATABASE_URL = os.environ.get("DATABASE_URL")

app = FastAPI(
    title="Microservicio de Mantenimientos",
    description="API de solo lectura para los mantenimientos de equipos.",
    version="1.0.0",
)

# CORS abierto para que cualquier cliente (por ejemplo Django) pueda consumirlo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection():
    """Abre una conexion nueva a PostgreSQL/Supabase."""
    if not DATABASE_URL:
        raise RuntimeError(
            "La variable de entorno DATABASE_URL no esta configurada."
        )
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def serializar(registro):
    """Convierte tipos de PostgreSQL a tipos serializables en JSON."""
    resultado = {}
    for clave, valor in registro.items():
        if isinstance(valor, (datetime, date)):
            resultado[clave] = valor.isoformat()
        elif isinstance(valor, Decimal):
            resultado[clave] = float(valor)
        else:
            resultado[clave] = valor
    return resultado


def error_json(mensaje, detalle, status_code):
    """Respuesta JSON uniforme ante errores."""
    return JSONResponse(
        status_code=status_code,
        content={"error": mensaje, "detalle": detalle},
    )


@app.get("/")
def salud():
    """Mensaje de salud del servicio."""
    return {
        "servicio": "microservicio-mantenimientos",
        "estado": "ok",
        "mensaje": "El microservicio de mantenimientos esta en linea.",
    }


@app.get("/mantenimientos")
def listar_mantenimientos():
    """Devuelve todos los mantenimientos en JSON."""
    try:
        conexion = get_connection()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, equipo_id, descripcion, tecnico, fecha, costo
                    FROM mantenimientos
                    ORDER BY fecha DESC, id DESC;
                    """
                )
                filas = cursor.fetchall()
        finally:
            conexion.close()
    except RuntimeError as exc:
        return error_json("Configuracion incompleta", str(exc), 500)
    except psycopg2.Error as exc:
        return error_json(
            "No se pudo consultar la base de datos", str(exc), 503
        )
    except Exception as exc:  # noqa: BLE001
        return error_json("Error inesperado del servidor", str(exc), 500)

    return [serializar(fila) for fila in filas]


@app.get("/mantenimientos/{equipo_id}")
def listar_mantenimientos_por_equipo(equipo_id: int):
    """Devuelve los mantenimientos de un equipo especifico en JSON."""
    try:
        conexion = get_connection()
        try:
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, equipo_id, descripcion, tecnico, fecha, costo
                    FROM mantenimientos
                    WHERE equipo_id = %s
                    ORDER BY fecha DESC, id DESC;
                    """,
                    (equipo_id,),
                )
                filas = cursor.fetchall()
        finally:
            conexion.close()
    except RuntimeError as exc:
        return error_json("Configuracion incompleta", str(exc), 500)
    except psycopg2.Error as exc:
        return error_json(
            "No se pudo consultar la base de datos", str(exc), 503
        )
    except Exception as exc:  # noqa: BLE001
        return error_json("Error inesperado del servidor", str(exc), 500)

    return [serializar(fila) for fila in filas]
