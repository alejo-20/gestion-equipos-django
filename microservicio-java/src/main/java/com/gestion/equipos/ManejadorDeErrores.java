package com.gestion.equipos;

import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Traduccion de excepciones a respuestas JSON.
 *
 * Sin esto Spring devuelve su pagina de error en HTML, que no sirve ni para un
 * curl ni para Django: la vista de Django hace `respuesta.json()` y una respuesta
 * HTML levanta un error de parseo en vez de cair limpiamente al siguiente
 * microservicio de la cadena.
 *
 * En especial, una falla de base de datos se responde con 503 y no con 500: el 503
 * dice "no se pudo leer la base ahora, reintenten", que es el caso real, y Django
 * trata cualquier estado >= 500 como fallo y avanza al Java -> PHP -> ORM.
 */
@RestControllerAdvice
public class ManejadorDeErrores {

    private static final Logger log = LoggerFactory.getLogger(ManejadorDeErrores.class);

    /** Error de validacion del @Valid: 400 con el detalle por campo. */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> validacion(MethodArgumentNotValidException ex) {
        Map<String, String> errores = new LinkedHashMap<>();
        ex.getBindingResult().getFieldErrors()
                .forEach(error -> errores.put(error.getField(), error.getDefaultMessage()));

        Map<String, Object> cuerpo = new LinkedHashMap<>();
        cuerpo.put("error", "Los datos del equipo no son validos.");
        cuerpo.put("campos", errores);
        return ResponseEntity.badRequest().body(cuerpo);
    }

    /** Id con formato invalido en el path (por ejemplo /equipos/abc). */
    @ExceptionHandler(NumberFormatException.class)
    public ResponseEntity<Map<String, Object>> idInvalido(NumberFormatException ex) {
        return ResponseEntity.badRequest().body(Map.of(
                "error", "El id debe ser un numero entero."));
    }

    /**
     * Cualquier otro fallo, incluida la base de datos. Se registra completo en el
     * log del contenedor (que es donde se mira cuando algo se cae) pero al cliente
     * se le devuelve un mensaje generico, sin filtrar detalles de la base.
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> inesperado(Exception ex) {
        log.error("Fallo inesperado atendiendo una peticion de equipos", ex);

        Map<String, Object> cuerpo = new LinkedHashMap<>();
        cuerpo.put("error", "No se pudo completar la operacion sobre la base de datos.");
        cuerpo.put("detalle", ex.getMessage());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(cuerpo);
    }
}
