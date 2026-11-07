# Las pruebas

md-to-pdf tiene dos clases de pruebas:

- `tests/test_thesis.py` comprueba el HTML y el PDF con `assert`. Corre con `uv run python tests/test_thesis.py`.
- `tests/matrix.py` genera los documentos de la matriz, `tests/a1.md` … `a5.md`, y sus PDF. Corre con `uv run python tests/matrix.py`. Una persona mira los PDF.

## La matriz

Muchas opciones no son independientes: la portada, el índice y el salto de página deciden juntos qué abre la página 1. Un documento por opción no prueba esas combinaciones. Un documento por combinación son 2¹³ documentos.

La matriz prueba las 4 combinaciones de cada par de opciones que interactúan, con el menor número de documentos.

`tests/matrix.py` es la fuente. Guarda los factores, las aristas y el coloreado, y `check()` comprueba la cobertura cada vez que corre.

### Los factores

Un factor es una opción con dos niveles: 0 es el valor por defecto, y 1 es el otro valor. `FACTORS` guarda el front matter de cada nivel. Los 13 factores son la portada, el índice, las listas, `page_break`, el nivel base de los títulos, la numeración, la posición de la leyenda, `locale`, la bibliografía, el tamaño de página, `toc_depth`, `code_theme` y el `.theme`.

Todos los documentos tienen el mismo cuerpo, `tests/body.md`, en español. El cuerpo usa cada función: siglas, notas, citas, bloques de código, tablas, figuras y fórmulas. Una tabla es más ancha que el texto a propósito.

### Las aristas

Una arista une dos factores que lee el mismo código. `EDGES` guarda las aristas, y un comentario dice el código de cada una. Un par sin arista no necesita sus 4 combinaciones.

### La cota inferior

La portada, el índice, las listas y `page_break` forman un clique: cada par tiene una arista. 4 columnas binarias con las 4 combinaciones en cada par necesitan 5 filas. `check()` comprueba por búsqueda exhaustiva que 4 filas no bastan. La matriz necesita 5 documentos como mínimo.

### El coloreado

Dos factores sin arista comparten una columna sin perder cobertura. `COLOUR` da un color a cada factor, y dos factores con arista tienen colores distintos. El grafo tiene un coloreado con 4 colores.

Cada color usa una de estas 4 columnas de 5 filas. Cada par de columnas tiene las combinaciones 00, 01, 10 y 11:

```
00111  01011  01101  01110
```

Así, 5 documentos cubren todas las aristas, y 5 es la cota inferior.

## Un factor nuevo

1. Añade el factor a `FACTORS`, con el front matter de sus dos niveles.
2. Añade a `EDGES` cada par con un factor que lee el mismo código.
3. Dale un color en `COLOUR` sin arista con otro factor del mismo color.
4. Corre `tests/matrix.py`. `check()` falla si el coloreado o la cobertura no valen.

5 filas admiten 4 columnas como máximo, por el teorema de Kleitman y Spencer. Un quinto color necesita 6 filas, que admiten 10 columnas.

Una función nueva del cuerpo entra en `tests/body.md`.
