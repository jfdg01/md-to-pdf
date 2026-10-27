# Infográficos en los informes de md-to-pdf

Un infográfico cuenta una prueba entera en una figura, como una diapositiva: quién hace qué, por dónde pasa y qué ocurre. Una tabla que compara dos situaciones con medidas de unidades distintas (peticiones, milisegundos, CPU, memoria) se lee mejor como un infográfico. Una sola medida, o una serie en el tiempo, va en una gráfica.

Un infográfico es un SVG escrito a mano, y sigue el flujo, las trampas y los colores de `docs/charts.md`. Este doc tiene solo las reglas propias del infográfico. El ejemplo de referencia es `fig_prueba_conjunta()` en `3.3/graficos.py` del repo `jfdg01/actividades-asn`.

## La estructura

1. **El escenario**, en una franja arriba. Cada actor tiene su icono, su nombre y una línea gris de detalle. Las flechas van de los actores al sistema, y su grosor dice el volumen del tráfico.
2. **Las tarjetas**, una por situación, lado a lado. Cada tarjeta tiene un título en negrita y un lema gris que dice la causa del resultado.
3. **Las filas** de cada tarjeta, una por actor y en el mismo orden en cada tarjeta. Cada fila tiene el icono del actor, una etiqueta en mayúsculas y una cifra grande.

## Las piezas

| Pieza | Regla |
|---|---|
| Icono | El color de su actor, el mismo en el escenario y en las tarjetas. Una persona es un círculo y unos hombros. Un servidor es una caja con dos ranuras. |
| Cifra grande | 24 px, en negrita y en tinta, con su nota gris en la misma línea. Un `<text>` con dos `<tspan>` pone la nota detrás de la cifra sin medir el texto. |
| Medidor | Una pista de 8 px del color de la rejilla, con el relleno del color del actor. Muestra una proporción, o un consumo frente a su límite escrito debajo. |
| Tarjeta | Radio de 12 px, fondo de la superficie y borde de la rejilla. La caja del sistema lleva el borde del eje, y cada pieza es una píldora del color de la rejilla. |

El texto va en tinta o en gris, nunca en el color de un actor. Un infográfico tiene tres actores como mucho, con los tres colores de `docs/charts.md`. El texto del informe dice de dónde sale cada cifra y cuántas ejecuciones hubo.
