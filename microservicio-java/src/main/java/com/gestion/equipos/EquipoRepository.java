package com.gestion.equipos;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Repositorio de Spring Data JPA.
 *
 * Spring genera la implementacion en tiempo de ejecucion a partir de la firma del
 * metodo, asi que no hace falta escribir ni una linea de SQL. Los nombres de los
 * metodos se interpretan: `findByNombre` arma un WHERE nombre = ?, `findAll` trae
 * todo, `save` inserta si el id es null y actualiza si no lo es, y `deleteById`
 * borra.
 */
public interface EquipoRepository extends JpaRepository<Equipo, Long> {

    List<Equipo> findAllByOrderByIdAsc();
}
