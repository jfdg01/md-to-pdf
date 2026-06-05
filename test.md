# Documento de prueba integral

**Asignatura:** Verificación del conversor
**Máster en Desarrollo de Software**
**Curso:** 2025/2026
**Autor:** Usuario de Prueba

---

## 1. Introducción

Este documento cubre todos los elementos que el conversor puede generar.
Sirve como herramienta de verificación visual: cada sección comprueba
un aspecto distinto del PDF resultante.

### 1.1 Propósito

El objetivo es confirmar que portada, índice, cabecera, pie, fuentes,
saltos de página y numeración automática de figuras y tablas funcionan
correctamente.

A continuación se muestra la primera imagen del documento:

![Logo de prueba — sección 1, figura 1](logo_uja.webp)

Y la segunda imagen de esta sección:

![Logo de prueba — sección 1, figura 2](logo_uja.webp)

### 1.2 Primera tabla de la sección

| Elemento        | Estado esperado          | Notas                        |
|-----------------|--------------------------|------------------------------|
| Portada         | Título, autor, asignatura| Con logo si existe           |
| Índice          | Secciones y subsecciones | Con hipervínculos            |
| Cabecera/pie    | Título · Asignatura / Autor + pág. | Fuente embebida   |
| Figuras         | Figura x.y bajo la imagen| Contador por sección         |
| Tablas          | Tabla x.y encima         | Contador por sección         |

## 2. Formato de texto

El cuerpo admite el Markdown habitual.

### 2.1 Énfasis

- **Negrita** con doble asterisco.
- *Cursiva* con un asterisco.
- ***Negrita y cursiva*** combinadas.
- ~~Tachado~~ (no soportado por el conversor, se muestra en bruto).
- `código en línea` con acento grave.

### 2.2 Párrafos y flujo

Un párrafo normal tiene una separación cómoda con el siguiente.
Este texto es suficientemente largo para comprobar que el interlineado
de 1,6 y el tamaño de 13 pt resultan legibles en el PDF impreso.

Segundo párrafo de la misma subsección, sin ninguna marca especial.

### 2.3 Hipervínculos

Un enlace externo: [Página de inicio de Python](https://www.python.org).
Los hipervínculos del índice y del outline del PDF son internos y se
generan automáticamente; no es necesario escribirlos a mano.

## 3. Listas

### 3.1 Lista no ordenada con guiones

- Primer elemento de nivel 1
- Segundo elemento de nivel 1
  - Subelemento anidado A
  - Subelemento anidado B
    - Tercer nivel de anidamiento
- Tercer elemento de nivel 1

### 3.2 Lista ordenada

1. Paso uno
2. Paso dos
3. Paso tres
   1. Subpaso 3.1
   2. Subpaso 3.2
4. Paso cuatro

### 3.3 Lista con texto largo

- Este ítem tiene un texto deliberadamente largo para comprobar que el ajuste
  de línea funciona correctamente dentro del elemento de lista sin romper
  el sangrado ni el interlineado.
- Ítem corto.
- Otro ítem con **negrita** y `código` en línea mezclados con texto normal.

## 4. Bloques de código

### 4.1 Código sin lenguaje

```
$ md-to-pdf informe.md
  informe.md → informe.pdf [OK, 142 KB]
```

### 4.2 Python con resaltado de sintaxis

```python
def add_figure_table_numbers(html):
    section = [0]
    figs = [0]
    tabs = [0]
    pattern = re.compile(r'<h2\b[^>]*>|<img\b[^>]*/?>|<table\b[^>]*>')

    def sub(m):
        tag = m.group(0)
        lo = tag.lower()
        if lo.startswith('<h2'):
            section[0] += 1
            figs[0] = 0
            tabs[0] = 0
            return tag
        if lo.startswith('<img'):
            figs[0] += 1
            return f'<figure>{tag}<figcaption>Figura {section[0]}.{figs[0]}</figcaption></figure>'
        return tag

    return pattern.sub(sub, html)
```

### 4.3 Bash

```bash
# Instalar dependencias y lanzar la conversión
cd ~/.local/scripts/md-to-pdf
bash install.sh
md-to-pdf documento.md
```

### 4.4 JSON

```json
{
  "id": 1,
  "method": "Page.printToPDF",
  "params": {
    "printBackground": true,
    "paperWidth": 8.27,
    "paperHeight": 11.69,
    "marginTop": 1.15
  }
}
```

## 5. Tablas

### 5.1 Tabla básica

| Nombre   | Tipo     | Valor por defecto |
|----------|----------|-------------------|
| `margin` | `float`  | `1.15`            |
| `font`   | `string` | `Source Serif 4`  |
| `size`   | `int`    | `13`              |

### 5.2 Tabla con alineación

| Izquierda    | Centro       | Derecha    |
|:-------------|:------------:|----------:|
| texto        | texto        | 1 234,56 € |
| texto largo  | texto largo  | 99,00 €    |
| A            | B            | 0,01 €     |

## 6. Imágenes

### 6.1 Primera imagen de la sección

Esta imagen recibe la etiqueta **Figura 6.1**:

![Primera imagen de la sección 6](logo_uja.webp)

### 6.2 Segunda imagen de la sección

Esta imagen recibe la etiqueta **Figura 6.2**:

![Segunda imagen de la sección 6](logo_uja.webp)

El contador se reinicia en la siguiente sección (`##`), por lo que
la primera imagen de la sección 7 será *Figura 7.1*.

## 7. Citas, separadores y elementos mixtos

### 7.1 Cita en bloque

> Esta es una cita en bloque (*blockquote*). Puede contener **texto con
> formato**, `código` e incluso varias líneas consecutivas que se unen
> en un único bloque visual con borde izquierdo y fondo gris claro.

> Segunda cita independiente, separada de la anterior.

### 7.2 Separador horizontal

El siguiente elemento es una línea horizontal (`---` en el Markdown):

---

El texto continúa tras el separador. Observa que el conversor ignora
el `---` inicial del documento (lo usa como separador portada/cuerpo),
pero dentro del cuerpo produce el `<hr>` habitual.

### 7.3 Tabla e imagen en la misma sección

Esta sección tiene los dos tipos para verificar que los contadores
son independientes:

| Columna 1 | Columna 2 | Columna 3 |
|-----------|-----------|-----------|
| A1        | B1        | C1        |
| A2        | B2        | C2        |

![Imagen junto a una tabla en sección 7](logo_uja.webp)

Los elementos anteriores deben aparecer como **Tabla 7.1** y
**Figura 7.1** respectivamente.
