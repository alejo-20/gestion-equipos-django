# Imagen del microservicio de equipos en PHP.
#
# No hay paso de build: PHP es un lenguaje interpretado, asi que la imagen solo
# necesita el interprete, la extension pdo_pgsql y el codigo. Por eso es una sola
# etapa.
#
# La imagen oficial de PHP no trae pdo_pgsql ni el servidor: se instalan con
# `docker-php-ext-install`, que compila la extension contra las fuentes que ya
# estan en la imagen. `pdo_pgsql` es la que permite hablar con Postgres via PDO.
#
# Las variables de entorno NO se hornean: se pasan con `docker run -e` o desde el
# panel del hosting.

FROM php:8.3-cli-alpine

# pdo_pgsql es el driver de PostgreSQL para PDO, que es lo que usa index.php, y
# hay que compilarlo: la imagen oficial de PHP no lo trae.
#
# Compilarlo NO es solo un `docker-php-ext-install`: la extension se compila
# contra las cabeceras de libpq (libpq-fe.h), que no estan en la imagen. Por eso
# primero se instala postgresql-dev en un grupo virtual `.build-deps`, se compila,
# y despues se borra ese grupo para no dejar herramientas de compilacion adentro.
# La biblioteca de ejecucion (libpq) se instala aparte y se queda, porque sin ella
# la extension compilada no carga.
#
# No se instala `pdo`: PHP 8.3 ya lo tiene compilado y `docker-php-ext-install pdo`
# falla con "pdo (pdo) is already loaded!".
RUN apk add --no-cache --virtual .build-deps postgresql-dev $PHPIZE_DEPS \
    && docker-php-ext-install pdo_pgsql \
    && apk del .build-deps \
    && apk add --no-cache libpq

WORKDIR /app

# La conexion sale del entorno, asi que se declara para documentarlo. No se
# escribe ninguna clave en la imagen.
ENV PORT=8083 \
    DB_HOST=localhost \
    DB_PORT=5432 \
    DB_NAME=gestion_equipos \
    DB_USER=gestion \
    DB_PASSWORD= \
    EQUIPOS_TABLE=equipo

COPY index.php ./
COPY openapi.yaml ./
COPY public ./public

# Usuario sin privilegios: si alguien logra ejecutar codigo adentro del
# contenedor, no puede escribir en el sistema de archivos.
RUN addgroup -S app && adduser -S -G app app && chown -R app:app /app
USER app

EXPOSE 8083

# OJO: `php -S` es monoproceso y de un solo hilo. No existe opcion de workers ni
# variable de entorno para abrir procesos hijos, asi que este servicio atiende una
# peticion a la vez. Para atender varias en paralelo habria que usar php-fpm con
# nginx por delante, o correr varias replicas del contenedor; con el volumen de
# trafico de esta demo el servidor embebido alcanza y sobra.
CMD ["sh", "-c", "exec php -S 0.0.0.0:${PORT} -t . index.php"]
