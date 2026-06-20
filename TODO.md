# TODO — Próximas funcionalidades

Mejoras a implementar **una por una**, con un **commit individual** por cada una.

- [x] **4.** Referencias cruzadas y numeración automática de secciones — *completado*
- [x] **5.** Tamaño de página y márgenes configurables desde el front matter — *completado*
- [x] **10.** Modo `--watch` (regenerar al guardar) — *completado*
- [x] **6.** Bibliografía / citas — *completado*

---

## 4. Referencias cruzadas y numeración automática de secciones

**Qué:** dejar de numerar las secciones a mano (`## 1. Introducción`) y permitir
enlazar a figuras/tablas/bloques por su número.

- **Autonumeración de secciones:** numerar automáticamente los `##` (1, 2, 3…) y
  los `###` (1.1, 1.2…) durante el render, sin que el autor escriba el número en
  el Markdown. Debe reflejarse igual en el índice de contenidos y en los
  marcadores (outline) del PDF.
  - Configurable desde el front matter (p. ej. `numbering: true|false`) para no
    romper documentos que ya traen la numeración escrita a mano.
- **Referencias cruzadas:** una sintaxis tipo `[ver Figura 2.1]` o un marcador
  (`[[fig-2-1]]`, `@fig:...`) que se convierta en un enlace al ancla ya existente
  (`fig-2-1`, `tab-2-1`, `code-2-1`, que ya genera `add_asset_numbers`). El texto
  visible debería poder mostrar el número del elemento.
- Tener cuidado con el reinicio de contadores de figuras/tablas/código en cada
  `##` (lógica ya presente en `add_asset_numbers`).

---

## 5. Tamaño de página y márgenes configurables desde el front matter

**Qué:** hoy el tamaño (A4) y los márgenes están fijos como constantes
(`PAGE_MARGIN`, `size: A4` en `page_css` y en `cover_html`).

- Nuevas claves de front matter (con alias en español), p. ej.:
  - `page_size: a4 | letter | legal | a5 …` (def. `a4`).
  - `margins: <css>` (p. ej. `1.15in 0.85in 0.95in 0.85in`) o claves separadas
    (`margin_top`, `margin_right`…).
  - `orientation: portrait | landscape` (opcional).
- Propagar el valor a **los tres sitios** que fijan el `@page`: `page_css` (cuerpo),
  `cover_html` (portada) y los `@page { size: ... }`.
- Validar valores desconocidos: avisar por consola y caer en el valor por defecto,
  igual que ya se hace con `code_theme` desconocido.
- Documentar las claves nuevas en la tabla de metadatos del `README.md`.

---

## 10. Modo *watch* (regenerar al guardar)

**Qué:** un flag `--watch` que vigile los `.md` y regenere el PDF
automáticamente cada vez que se guardan.

- Usar `watchdog` (añadir la dependencia con `uv add watchdog` y a
  `requirements.txt`).
- Comportamiento:
  - `md-to-pdf --watch` → vigila todos los `.md` del directorio actual.
  - `md-to-pdf --watch informe.md` → vigila solo ese fichero.
  - Al detectar cambios, reconvierte e informa con el mismo formato que ahora
    (`nombre.md → nombre.pdf [OK, NN KB]` / `[ERROR: …]`).
- *Debounce* para evitar dobles regeneraciones por varios eventos de guardado
  seguidos.
- No romper el comportamiento actual sin el flag (conversión única y salida).
- Salir limpiamente con Ctrl-C.

---

## 6. Bibliografía / citas

**Qué:** permitir citar fuentes en el cuerpo y generar automáticamente una sección
de **referencias** al final del documento. Alto valor para el uso académico
(informes, TFG, apuntes de la UJA).

- **Fichero de bibliografía:** nueva clave de front matter (con alias en español),
  p. ej. `bibliography: refs.bib` (ruta relativa al `.md`, como `logo`). Formato
  **BibTeX** (`.bib`).
- **Sintaxis de cita en el cuerpo:** estilo `[@clave]` (una cita) y `[@clave1; @clave2]`
  (varias). Cada cita se sustituye por su marca (numérica `[1]` o autor-año
  `(Pérez, 2020)`, según estilo) y **enlaza** a la entrada en la bibliografía,
  reutilizando el mismo mecanismo de anclas/enlaces internos del punto 4.
- **Sección de referencias:** generar al final un apartado *«Referencias»* (es) /
  *«References»* (en) — añadir las cadenas a `STRINGS` — que liste **solo las
  entradas citadas**, formateadas de forma consistente y con un ancla por entrada.
  - Debe integrarse con la autonumeración del punto 4 (¿cuenta como sección `##`
    numerada o como apartado sin número? Decidir y documentar).
  - Debe aparecer en el índice de contenidos y en los marcadores (outline).
- **Estilo de cita configurable:** clave `citation_style: numeric | author-year`
  (def. `numeric`). Validar valores desconocidos y avisar, como con `code_theme`.
- **Localización:** título de la sección y formato de cita respetando `locale`
  (`es`/`en`).
- **Dependencias:** valorar `pybtex` (parseo BibTeX) y/o `citeproc-py` (formateo
  según estilos CSL). Añadir con `uv` y a `requirements.txt`. Mantener el import
  perezoso (dentro de la función) si solo hace falta cuando hay `bibliography`,
  para no penalizar el arranque del resto de conversiones.
- **Robustez:** si una `[@clave]` no existe en el `.bib`, avisar por consola
  (igual que con los captions faltantes) y/o dejar la marca visible; documentar el
  comportamiento elegido.
- Documentar las claves nuevas en la tabla de metadatos del `README.md` con un
  ejemplo completo (`.bib` + citas en el cuerpo + sección resultante).

---

### Notas de proceso

- Implementar **en este orden**: 4 → 5 → 10.
- **Un commit por punto**, con mensaje claro y autocontenido.
- Mantener el estilo del código existente (comentarios en español, mismas
  convenciones de nombres y estructura).
- Usar `uv` para gestionar dependencias y entorno.
