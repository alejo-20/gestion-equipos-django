package com.gestion.equipos;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Endpoints REST de la tabla `equipo`.
 *
 * Es el microservicio Java del proyecto: Django lo consulta SEGUNDO, cuando Node
 * no responde, y es el destino del boton "Guardar con Java" del formulario.
 *
 * Las respuestas usan Map&lt;String, Object&gt; y no un tipo por endpoint porque el
 * JSON cambia de forma segun el resultado (envia "equipo" o manda "error"), y
 * `Map.of` no admite valores de tipos distintos si se quiere inferir el tipo.
 */
@RestController
@RequestMapping("/equipos")
@Tag(name = "equipos", description = "Operaciones sobre la tabla compartida `equipo`")
public class EquipoController {

    private final EquipoRepository repositorio;

    public EquipoController(EquipoRepository repositorio) {
        this.repositorio = repositorio;
    }

    @Operation(summary = "Lista todos los equipos",
            description = "Devuelve el inventario completo. Es el segundo recurso que "
                    + "prueba Django para leer; el primero es el microservicio Node.")
    @GetMapping
    public Map<String, List<EquipoResponse>> listar() {
        List<EquipoResponse> equipos = repositorio.findAllByOrderByIdAsc().stream()
                .map(EquipoResponse::desde)
                .toList();
        return Map.of("equipos", equipos);
    }

    @Operation(summary = "Devuelve un equipo por id")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "El equipo pedido."),
        @ApiResponse(responseCode = "404", description = "No existe un equipo con ese id.")
    })
    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> obtener(@PathVariable Long id) {
        Equipo equipo = repositorio.findById(id).orElse(null);
        if (equipo == null) {
            return noEncontrado(id);
        }
        return ResponseEntity.ok(Map.of("equipo", EquipoResponse.desde(equipo)));
    }

    @Operation(summary = "Inserta un equipo",
            description = "Es el destino del boton \"Guardar con Java\" del formulario de Django.")
    @ApiResponses({
        @ApiResponse(responseCode = "201", description = "Equipo creado, con su id."),
        @ApiResponse(responseCode = "400", description = "Faltan campos o `tipo` no es valido.",
                content = @Content(schema = @Schema(implementation = Map.class)))
    })
    @PostMapping
    public ResponseEntity<Map<String, Object>> crear(@Valid @RequestBody EquipoRequest pedido) {
        Equipo equipo = new Equipo();
        equipo.setNombre(pedido.nombre());
        equipo.setTipo(pedido.tipo());
        equipo.setDisponible(pedido.disponibleOmitido());

        Equipo guardado = repositorio.save(equipo);

        // 201 Created + cabecera Location, que es lo que corresponde a un POST que
        // creo un recurso.
        return ResponseEntity
                .created(URI.create("/equipos/" + guardado.getId()))
                .body(Map.of("equipo", EquipoResponse.desde(guardado)));
    }

    @Operation(summary = "Actualiza un equipo existente")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Equipo actualizado."),
        @ApiResponse(responseCode = "400", description = "Faltan campos o `tipo` no es valido."),
        @ApiResponse(responseCode = "404", description = "No existe un equipo con ese id.")
    })
    @PutMapping("/{id}")
    public ResponseEntity<Map<String, Object>> actualizar(
            @PathVariable Long id, @Valid @RequestBody EquipoRequest pedido) {

        Equipo equipo = repositorio.findById(id).orElse(null);
        if (equipo == null) {
            return noEncontrado(id);
        }

        equipo.setNombre(pedido.nombre());
        equipo.setTipo(pedido.tipo());
        equipo.setDisponible(pedido.disponibleOmitido());

        return ResponseEntity.ok(
                Map.of("equipo", EquipoResponse.desde(repositorio.save(equipo))));
    }

    @Operation(summary = "Elimina un equipo")
    @ApiResponses({
        @ApiResponse(responseCode = "200", description = "Equipo eliminado."),
        @ApiResponse(responseCode = "404", description = "No existe un equipo con ese id.")
    })
    @DeleteMapping("/{id}")
    public ResponseEntity<Map<String, Object>> eliminar(@PathVariable Long id) {
        if (!repositorio.existsById(id)) {
            return noEncontrado(id);
        }
        repositorio.deleteById(id);
        return ResponseEntity.ok(Map.of("eliminado", id));
    }

    /** Respuesta 404 con el mensaje de error en el mismo formato que el resto. */
    private ResponseEntity<Map<String, Object>> noEncontrado(Long id) {
        Map<String, Object> cuerpo = new LinkedHashMap<>();
        cuerpo.put("error", "No existe un equipo con id " + id + ".");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(cuerpo);
    }
}
