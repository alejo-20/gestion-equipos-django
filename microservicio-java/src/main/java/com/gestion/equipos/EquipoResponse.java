package com.gestion.equipos;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * Respuesta de un equipo.
 *
 * El JSON tiene que ser IDENTICO al de los otros dos microservicios, porque Django
 * los mete en el mismo context sin preguntar de donde vinieron:
 *
 *   {"equipos": [{"id": 1, "nombre": "...", "tipo": "laptop", "disponible": true}]}
 *
 * `tipo` va como clave ("laptop"), no como etiqueta legible ("Laptop"): la etiqueta
 * depende del idioma y Django la deriva con get_tipo_display() sobre su modelo.
 */
@Schema(name = "Equipo", description = "Un equipo del inventario.")
public record EquipoResponse(

    @Schema(example = "7")
    Long id,

    @Schema(example = "Notebook Lenovo ThinkPad")
    String nombre,

    @Schema(example = "laptop", allowableValues = {"laptop", "proyector", "tablet", "camara"})
    String tipo,

    @Schema(example = "true")
    boolean disponible
) {

    public static EquipoResponse desde(Equipo equipo) {
        return new EquipoResponse(
                equipo.getId(),
                equipo.getNombre(),
                equipo.getTipo(),
                equipo.isDisponible());
    }
}
