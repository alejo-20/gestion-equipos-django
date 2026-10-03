package com.gestion.equipos;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Microservicio de equipos en Spring Boot.
 *
 * Expone el CRUD de la tabla `equipo`, que es la MISMA tabla que usan el proyecto
 * Django (por su ORM) y los microservicios Node (por `pg`) y PHP (por PDO). Por
 * eso la conexion sale de variables de entorno y no esta escrita en el codigo.
 *
 * Es el SEGUNDO de la cadena de lectura de Django: si el microservicio Node no
 * responde, Django recurre a este.
 */
@SpringBootApplication
public class EquiposApplication {

    public static void main(String[] args) {
        SpringApplication.run(EquiposApplication.class, args);
    }
}
