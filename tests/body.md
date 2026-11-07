*[PDF]: Portable Document Format
*[IEEE]: Institute of Electrical and Electronics Engineers

## Texto

**Negrita**, *cursiva*, `código`, un [enlace](https://www.python.org), un
PDF[^pdf] y un [enlace sobre el PDF](https://example.org). Citas IEEE
[@perez2024], [@spring] y [@brown2018; @dibo2026].

[^pdf]: Una nota al pie.

> Una cita con **formato** en dos líneas
> que forman un solo bloque.

---

- Uno
  - Uno a
    - Uno a i

Una lista numerada:

1. Paso
   1. Subpaso

### Subsección

#### Nivel 4

##### Nivel 5, fuera del índice por defecto

<!-- toc -->
##### Nivel 5 forzado al índice

<!-- no-toc -->
### Fuera del índice

## Código

Los bloques son el [[code-2-1]], el [[code-2-2]], el [[code-2-3]], el
[[code-2-4]], el [[code-2-5]] y el [[code-2-6]].

<!-- caption: Sin lenguaje -->
<!-- file: terminal -->
```
$ md-to-pdf informe.md
```

<!-- caption: Python -->
<!-- file: src/fib.py -->
```python
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
```

<!-- caption: JSON con tema propio -->
<!-- code-theme: solarized-light -->
```json
{ "printBackground": true, "paperWidth": 8.27 }
```

<!-- caption: Una valla yml -->
```yml
# comentario
version: 1.2
enabled: true
anchor: &base
  key: value
copy: *base
```

<!-- caption: PHP sin etiqueta de apertura -->
```php
echo strtoupper($nombre);
```

El bloque siguiente va pegado a este párrafo:

<!-- keep -->
<!-- caption: Pegado al párrafo -->
```python
print("hola")
```

## Tablas

La [[tab-3-1]], la [[tab-3-2]] y la [[tab-3-3]], que es más ancha que el texto.

<!-- caption: Básica -->
| Nombre   | Tipo    |
|----------|---------|
| `margin` | `float` |

<!-- caption: Alineación -->
| Izquierda | Centro | Derecha |
|:----------|:------:|--------:|
| texto     | texto  | 1.234,5 |

<!-- caption: Ancha -->
| Clave | Valor |
|-------|-------|
| `una_clave_muy_larga_que_no_se_puede_partir_en_dos_lineas_nunca` | `otro_identificador` |

## Figuras

La [[fig-4-1]] tiene la leyenda en un comentario, y la [[fig-4-2]] en el texto
alternativo. La [[fig-4-3]] es una fila de tres imágenes, y la [[fig-4-4]] una
fila de cuatro, el máximo.

<!-- caption: Una montaña nevada -->
![Montaña](../assets/img/foto1.jpg)

![Un bosque desde el aire](../assets/img/foto2.jpg)

<!-- caption: Fila de tres -->
![A](../assets/img/foto1.jpg) ![B](../assets/img/foto2.jpg) ![C](../assets/img/foto3.jpg)

<!-- caption: Fila de cuatro -->
![A](../assets/img/foto1.jpg) ![B](../assets/img/foto2.jpg) ![C](../assets/img/foto3.jpg) ![D](../assets/img/foto1.jpg)

## Fórmulas

La energía es $E = mc^2$, y la [[eq-5-1]] da la varianza. Un precio de $5 y
otro de $6 quedan como texto.

$$
\sigma^2 = \frac{1}{n} \sum_{i=1}^{n} (x_i - \bar{x})^2
$$
