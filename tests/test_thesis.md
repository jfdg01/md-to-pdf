---
title: Funciones de una tesis
subtitle: Leyenda encima, fórmulas, notas, siglas y referencias IEEE
author: Test User
bibliography: test_thesis.bib
caption_position: top
---

*[PDF]: Portable Document Format
*[IEEE]: Institute of Electrical and Electronics Engineers

## Introducción

Este documento genera un PDF[^pdf] con citas en estilo IEEE [@perez2024]. La
guía de Spring [@spring] y dos libros [@brown2018; @dibo2026] completan la
lista. La [[fig-1-1]] compara dos fotos, y la [[tab-1-1]] resume los datos.

[^pdf]: Un PDF conserva la maquetación en cualquier máquina.

<!-- caption: Antes y después del proceso -->
![Antes](../assets/img/foto1.jpg) ![Después](../assets/img/foto2.jpg) ![Detalle](../assets/img/foto3.jpg)

<!-- caption: Datos de la prueba -->
| Prueba | Resultado |
|--------|-----------|
| A      | 0,95      |
| B      | 0,87      |

## Método

La energía cumple $E = mc^2$, y la media es $\bar{x} = \frac{1}{n}\sum_i x_i$.
La [[eq-2-1]] da la varianza, y el [[code-2-1]] la calcula[^code].

[^code]: El código usa solo la librería estándar de Python.

$$
\sigma^2 = \frac{1}{n} \sum_{i=1}^{n} (x_i - \bar{x})^2
$$

<!-- caption: La varianza en Python -->
```python
def var(xs):
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)
```

Un precio de $5 y otro de $6 quedan como texto. El IEEE define el estilo.

$$ \int_0^1 x\,dx = \tfrac{1}{2} $$
