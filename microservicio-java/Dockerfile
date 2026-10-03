# Imagen del microservicio de equipos en Spring Boot.
#
# Son tres etapas. La primera compila el jar con Maven (descarga el JDK y todas
# las dependencias). La segunda arma una imagen "plana" con el jar y las
# dependencias ya resueltas. La tercera copia solo eso a un JRE: la imagen final
# no tiene ni Maven, ni el codigo fuente, ni el cache de ~/.m2, asi que pesa una
# fraccion y tiene menos superficie de ataque.
#
# La variable de entorno NO se hornea en la imagen: se pasa en `docker run -e`
# o desde el panel del hosting. Por eso la imagen sirve igual para cualquier base.

# --- Etapa 1: compilar -------------------------------------------------------
FROM maven:3.9-eclipse-temurin-17 AS compilar
WORKDIR /build

# Se copia primero solo el pom.xml para que la capa de dependencias se
# aproveche mientras el pom no cambie: cambiar un .java no vuelve a descargar
# todo el arbol de Spring.
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -DskipTests package

# --- Etapa 2: preparar el runtime --------------------------------------------
FROM eclipse-temurin:17-jre AS preparar
WORKDIR /app

# Se copia el jar y las dependencias ya resueltas desde la cache de Maven, en vez
# de volver a resolverlas en la imagen final.
COPY --from=compilar /root/.m2/repository /tmp/m2
COPY --from=compilar /build/target/*.jar /app/app.jar
RUN cp -r /tmp/m2/* /app/ && rm -rf /tmp/m2 /app/app.jar.original

# --- Etapa 3: imagen final ---------------------------------------------------
FROM eclipse-temurin:17-jre
WORKDIR /app

# Puerto por defecto del servicio. Se puede sobreescribir con -e PORT=..., que es
# como lo publican los hosting de contenedores.
ENV PORT=8081
ENV JAVA_OPTS=""

COPY --from=preparar /app /app

# Usuario sin privilegios: si alguien logra ejecutar codigo adentro del
# contenedor, no puede escribir en el sistema de archivos.
RUN useradd --system --uid 1001 spring && chown -R spring:spring /app
USER spring

EXPOSE 8081

# El jar se ejecuta con sh -c para que JAVA_OPTS se expanda como variable de
# entorno; con la forma de exec directa ("java", "-jar", ...) no se expande.
ENTRYPOINT ["sh", "-c", "exec java $JAVA_OPTS -jar /app/app.jar"]
