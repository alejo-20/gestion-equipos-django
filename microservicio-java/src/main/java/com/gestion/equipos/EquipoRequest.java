package com.gestion.equipos;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * Cuerpo de entrada de POST /equipos y PUT /equipos/{id}.
 *
 * Es un record (inmutable) y a proposito NO es la entidad JPA: si el controller
 * recibiera la entidad, Hibernate podria enlazar un id que mande el cliente a una
 * fila existente (un mass assignment). Con un record separado, el id no se puede
 * tocar desde el JSON.
 *
 * Las anotaciones de Bean Validation se ejecutan automaticamente antes de entrar
 * al controller (@Valid), asi que un cuerpo invalido devuelve 400 sin llegar al
 * repositorio.
 *
 * `disponible` se declara Boolean (objeto) y no boolean (primitivo) para poder
 * distinguir "no vino" de "vino false": si fuera primitivo, Jackson lo
 * inicializaria en false y un POST sin el campo crearia el equipo como prestado.
 */
public record EquipoRequest(

    @Schema(description = "Nombre del equipo.", example = "Notebook Lenovo ThinkPad")
    @NotBlank(message = "El campo \"nombre\" es obligatorio.")
    @Size(max = 100, message = "El campo \"nombre\" no puede superar los 100 caracteres.")
    String nombre,

    @Schema(description = "Tipo de equipo.", example = "laptop",
            allowableValues = {"laptop", "proyector", "tablet", "camara"})
    @NotBlank(message = "El campo \"tipo\" es obligatorio.")
    @Pattern(regexp = "laptop|proyector|tablet|camara",
             message = "El campo \"tipo\" debe ser uno de: laptop, proyector, tablet, camara.")
    String tipo,

    @Schema(description = "Si el equipo esta disponible. Si no se manda, vale true.")
    Boolean disponible
) {

    /** El mismo default que el modelo Django: un equipo nuevo arranca disponible. */
    public boolean disponibleOmitido() {
        return disponible == null || disponible;
    }
}
