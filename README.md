# md-to-pdf

Convierte ficheros Markdown en un PDF con **portada**, **índice navegable**,
**índices de figuras/tablas/código** y **cabecera/pie** en cada página. Sirve para
informes, manuales, apuntes o cualquier documento estructurado.

El render lo hace **WeasyPrint** (Python puro, sin navegador): rápido, ligero y
con el mismo resultado en cualquier máquina. Las fuentes (Source Serif 4, Space
Grotesk, Space Mono) viajan con el repositorio en `assets/fonts/`.

---

## Requisitos

- **Python 3** (3.10+).
- **[uv](https://docs.astral.sh/uv/)** para gestionar el entorno y las
  dependencias. Si no lo tienes:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
  # Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- Las librerías de sistema de WeasyPrint (Pango/Cairo). En Ubuntu/Debian:
  ```bash
  sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0
  ```
  En Windows se instalan con WeasyPrint según su documentación (GTK runtime).

Las dependencias de Python (`markdown`, `weasyprint`, `pypdf`, `watchdog`,
`pygments`, `pybtex`) se declaran en `pyproject.toml` y se fijan en `uv.lock`; `uv sync` las instala en un
entorno virtual propio (`.venv/`) de forma reproducible.

---

## Instalación

El instalador llama a `uv sync` (crea el `.venv` e instala las dependencias del
lockfile) y registra el comando global `md-to-pdf`.

### Linux / Ubuntu
```bash
cd ~/.local/scripts        # o donde tengas clonado el repo
bash install.sh
```
Esto enlaza `md-to-pdf` en `~/.local/bin`. Asegúrate de que ese directorio está
en tu `PATH` (si no, añade a `~/.bashrc`):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Windows
```powershell
cd $env:USERPROFILE\Documents\md-to-pdf   # ruta del repo
.\install.ps1
```
Añade la carpeta del repo al `PATH` de usuario. **Abre una terminal nueva** para
que el comando `md-to-pdf` quede disponible.

> El `.venv/` es propio de cada máquina y está en `.gitignore`. Ejecuta el
> instalador una vez por equipo tras clonar.

---

## Uso

```bash
# Convierte UN fichero (genera informe.pdf junto al .md)
md-to-pdf informe.md

# Convierte VARIOS ficheros
md-to-pdf tema1.md tema2.md

# Convierte TODOS los .md de un directorio (sin recursión)
md-to-pdf apuntes/

# El directorio actual también vale
md-to-pdf .
```

Cada PDF se escribe junto a su `.md` de origen, con el mismo nombre.

### Nombre del PDF de salida (`-o` / `--output`)

Por defecto el PDF se llama igual que el `.md` y se escribe junto a él. Para
elegir otro nombre o ruta, usa `-o` (o `--output`). Funciona delante o detrás del
fichero de entrada:

```bash
# Elige el nombre del PDF generado
md-to-pdf informe.md -o memoria-final.pdf

# El orden de los argumentos da igual; admite también una ruta
md-to-pdf -o /tmp/salida.pdf informe.md
```

`-o` **solo se aplica al convertir un único `.md`**: si pasas varios ficheros o un
directorio, no se puede dar un mismo nombre a todos, así que se avisa por consola
y la opción se ignora (cada PDF se escribe junto a su `.md`).

### Modo vigilancia (`--watch`)

Con `--watch`, el conversor se queda observando y **regenera el PDF cada vez que
guardas** el `.md`, con el mismo formato de salida que la conversión única:

```bash
# Vigila solo un fichero
md-to-pdf --watch informe.md

# Vigila un directorio entero (incluidos los .md que crees después)
md-to-pdf --watch apuntes/
```

Hace una conversión inicial al arrancar y aplica un pequeño *debounce* para no
regenerar dos veces ante guardados muy seguidos. Sal con **Ctrl-C**.

---

## Cómo estructurar el Markdown

El documento empieza con un bloque de **front matter** (metadatos `clave: valor`
entre líneas `---`), seguido del **cuerpo**:

```markdown
---
title: Título del documento
subtitle: Un subtítulo opcional
comment: Una línea libre (fecha, curso, nota…)
author: Tu Nombre
logo: imagenes/portada.png
locale: es
---

## Introducción

Texto de la primera sección...

### Un subapartado

Más texto...

## Siguiente sección

...
```

Las secciones se numeran solas (ver más abajo), así que **no escribas el número**
en los encabezados.

### Metadatos del front matter

| Clave      | Para qué sirve                                            | Aparece en        |
|------------|----------------------------------------------------------|-------------------|
| `title`    | Título del documento (único obligatorio)                 | Portada + cabecera|
| `subtitle` | Subtítulo en cursiva                                      | Portada + cabecera|
| `comment`  | Línea libre adicional (fecha, curso, nota…)              | Portada           |
| `author`   | Autor                                                     | Portada + pie     |
| `logo`     | Ruta a **cualquier** imagen para la portada              | Portada           |
| `locale`   | `es` (def.) o `en`: idioma de "Figura/Figure", índices…  | Todo el documento |
| `code_theme`| Paleta de resaltado de código (ver más abajo)           | Bloques de código |
| `numbering`| Numera las secciones automáticamente (def. `true`; `false` lo desactiva) | Secciones + índice |
| `toc_depth`| Nivel máximo en el índice: `3` (`###`), `4` (`####`, def.) o `5` (`#####`) | Índice + marcadores |
| `page_size`| Tamaño de página: `a4` (def.), `a5`, `a3`, `letter`, `legal`… | Todo el documento |
| `orientation`| `portrait` (def.) o `landscape`                         | Todo el documento |
| `margins`  | Márgenes del cuerpo en CSS (`1.15in 0.85in 0.95in 0.85in`) | Todo el documento |
| `bibliography`| Ruta a un fichero `.bib` (BibTeX) para citas y referencias | Sección «Referencias» |
| `citation_style`| `numeric` (def., `[1]`) o `author-year` (`(Pérez, 2020)`) | Marcas de cita |

Se aceptan alias en español (`titulo`, `subtitulo`, `autor`, `imagen`, `idioma`,
`numeracion`, `profundidad_indice`, `tamaño`, `orientacion`, `margenes`,
`bibliografia`, `estilo_cita`…).
Si no defines `title`, se usa el primer encabezado `# ` del cuerpo. Si no defines
`logo`, la portada no lleva imagen; con `logo: none` también lo desactivas
explícitamente.

### Reglas del cuerpo

- **`## ` = sección.** Cada encabezado de nivel 2 empieza en una **página nueva**.
  Se numeran solas (`1.`, `2.`…); no escribas el número a mano (ver abajo).
- **`### ` = subsección.** No fuerza salto de página.
- **`#### ` y `##### ` = sub-subsección y nivel 5.** También se numeran solos
  (`1.1.1`, `1.1.1.1`).
- **El índice** lista automáticamente los `##`, `###` y `####` (hasta el nivel
  `toc_depth`, def. `####`), con enlaces que saltan a la sección al hacer clic, y
  el PDF incluye **marcadores** con esa jerarquía (ver «Profundidad del índice»).
- Funciona el Markdown habitual: **negrita**, *cursiva*, listas, tablas, `código`
  en línea y bloques con triple acento grave, citas.

### Numeración automática de secciones

Por defecto el conversor numera las secciones por ti: los `##` reciben `1.`,
`2.`, `3.`…, los `###` su `1.1`, `1.2`…, los `####` su `1.1.1` y los `#####` su
`1.1.1.1`. El número aparece igual en el cuerpo, en el índice de contenidos y en
los marcadores del PDF, así que **no lo escribas a mano** en los encabezados. Si
tu documento ya trae la numeración escrita, desactívala con `numbering: false`
para no duplicarla.

### Profundidad del índice

El índice de contenidos (y los marcadores del PDF) llega por defecto hasta los
`####` (nivel 4); los `#####` no aparecen. Cámbialo para **todo el documento** con
`toc_depth` en el front matter:

```yaml
toc_depth: 5   # incluye también los #####  (3 = solo hasta ###)
```

Y para un encabezado **concreto**, pon un comentario en la línea de encima:

```markdown
<!-- toc -->
##### Apartado que sí quiero en el índice

<!-- no-toc -->
### Apartado que NO quiero en el índice
```

`<!-- toc -->` fuerza la entrada de ese encabezado aunque su nivel exceda
`toc_depth`; `<!-- no-toc -->` la excluye aunque su nivel sí entre. Ambas marcas
afectan por igual al índice y a los marcadores del PDF.

### Referencias cruzadas

Para enlazar a una figura, tabla o bloque de código por su número, escribe su
ancla entre dobles corchetes: `[[fig-2-1]]`, `[[tab-2-1]]` o `[[code-2-1]]` (el
formato es `tipo-sección-índice`, las mismas anclas que se numeran solas). Se
convierte en un enlace cuyo texto visible es el número del elemento («Figura
2.1») y que salta a él al hacer clic. Si el ancla no existe, se avisa por consola
y la marca se deja tal cual para que la localices.

### Citas y bibliografía

Para citar fuentes, indica un fichero **BibTeX** en el front matter con
`bibliography:` (ruta relativa al `.md`, igual que `logo:`) y escribe las citas
en el cuerpo con `[@clave]`:

```markdown
---
title: Mi informe
bibliography: refs.bib
citation_style: numeric   # numeric (def.) | author-year
---

## Introducción

El método sigue trabajos previos [@perez2020]. Otros lo amplían
[@garcia2019; @lopez2021].
```

Con un `refs.bib` como:

```bibtex
@article{perez2020,
  author  = {Pérez, Juan Manuel and García, Ana},
  title   = {Métodos de evaluación automática},
  journal = {Revista de Computación},
  year    = {2020},
}
@book{garcia2019,
  author    = {García, Ana},
  title     = {Fundamentos de sistemas},
  publisher = {Editorial Técnica},
  year      = {2019},
}
```

Cada `[@clave]` se sustituye por una **marca enlazada** que salta a su entrada:

- `citation_style: numeric` (por defecto) → `[1]`, y varias juntas → `[2, 3]`.
- `citation_style: author-year` → `(Pérez y García, 2020)`, y varias →
  `(García, 2019; López et al., 2021)`.

Al final del documento se genera sola una sección **«Referencias»**
(«References» en `locale: en`) con **solo las entradas citadas**, formateadas de
forma consistente. Es una sección normal: **se numera** como una más (`8.
Referencias`) y aparece en el índice y en los marcadores del PDF. El orden es por
aparición (numeric) o alfabético por autor (author-year).

Si una `[@clave]` no está en el `.bib`, se avisa por consola y la marca se deja
visible (`[@clave]`) para que la localices. Si el nombre de `citation_style` es
desconocido, se avisa y se usa `numeric`. Las citas dentro de bloques o de
`código en línea` no se tocan.

### Tamaño de página y márgenes

Por defecto el documento es **A4 vertical**. Para cambiarlo, usa estas claves del
front matter:

- `page_size`: `a4` (def.), `a5`, `a3`, `letter`, `legal`, `b5`, `ledger`…
- `orientation`: `portrait` (def.) o `landscape`.
- `margins`: los márgenes del cuerpo como valor CSS (`top right bottom left`),
  p. ej. `margins: 1.15in 0.85in 0.95in 0.85in` o `margins: 2cm`. También puedes
  fijarlos por lado con `margin_top`, `margin_right`, `margin_bottom` y
  `margin_left` (los lados que no indiques conservan el valor por defecto).

```markdown
---
title: Apuntes en apaisado
page_size: letter
orientation: landscape
margins: 1in 1.25in
---
```

El tamaño y la orientación se aplican a **portada, índices y cuerpo** por igual.
Si el tamaño o la orientación son desconocidos, se avisa por consola y se usa el
valor por defecto (A4 / vertical).

### Listas

Usa el guion (`-`) como marcador y **no dejes líneas en blanco entre los
elementos** de una misma lista (eso produce espaciado de párrafo entre puntos).

### Imágenes, tablas y bloques de código

Se numeran como **Figura x.y**, **Tabla x.y** y **Bloque de código x.y**, donde
*x* es la sección (`##`) e *y* el índice dentro de ella (los contadores se
reinician en cada sección). Cada tipo tiene su propio índice al inicio.

**Toda figura, tabla y bloque de código debe llevar descripción**, o el conversor
se niega a generar el PDF (evita "Tabla x.y" vacías). La descripción se escribe
con un comentario HTML en la línea inmediatamente anterior:

```markdown
<!-- caption: Arquitectura general del sistema -->
![Diagrama de bloques](bloques.png)
```

- Las **imágenes** pueden usar su texto alternativo (`![texto](img)`) como
  descripción si no hay `<!-- caption: -->`.
- El comentario es invisible en cualquier otro visor de Markdown.

### Mantener un elemento junto al anterior

Coloca `<!-- keep -->` en la línea anterior a un elemento para forzarlo a quedarse
en la misma página que el contenido previo (en lugar de empujarlo a la siguiente).
Si no cabe entero, el propio elemento se parte. Útil para que un bloque de código
no se separe del texto que lo introduce.

```markdown
Como muestra la siguiente función:

<!-- keep -->
<!-- caption: Función principal -->
` ``python
def main():
    ...
` ``
```

### Resaltado de código: paletas y temas

El color del resaltado de sintaxis se controla a **dos niveles**.

**1. Tema de todo el documento — `code_theme` en el front matter.** Acepta:

- *(vacío)* o `custom` → la **paleta oscura apagada personalizada** (gris pizarra
  con acentos desaturados) definida en `src/md_to_pdf.py`. Es el valor por defecto.
- El nombre de **cualquier tema de Pygments**: `monokai`, `dracula`,
  `github-dark`, `solarized-light`, `solarized-dark`, `nord`, `gruvbox-dark`,
  `friendly`, `default`… (lista completa: `python -m pygments -L styles`).

```markdown
---
title: Mi documento
code_theme: monokai
---
```

Si el nombre no existe, se avisa por consola y se usa la paleta personalizada.

**2. Tema por bloque — `<!-- code-theme: NOMBRE -->`.** Colócalo en la línea
inmediatamente anterior a la valla ` ``` ` para que **ese bloque concreto** use
una paleta distinta de la del documento. Así pueden convivir varias paletas en
un mismo PDF:

```markdown
<!-- caption: Configuración (tema oscuro) -->
<!-- code-theme: monokai -->
` ``json
{ "printBackground": true }
` ``
```

Acepta los mismos valores que `code_theme` (un tema de Pygments o `custom`). Si
hay también un `<!-- caption: -->`, ponlo **encima** del `<!-- code-theme: -->`.

**Personalizar la paleta por defecto.** Edita el diccionario `CODE_PALETTE` cerca del
principio de `src/md_to_pdf.py`: cada clave (`keyword`, `string`, `comment`,
`function`, `number`, `background`…) es un color hex que puedes cambiar a tu
gusto. Los temas oscuros funcionan porque el `<pre>` interior es transparente y
el fondo lo pinta el contenedor con el color del tema.

---

## Notas

- Cabecera, pie, portada y cuerpo usan las fuentes incrustadas en `assets/fonts/`, así
  que el resultado es idéntico en cualquier sistema sin instalar nada. Si el
  título es muy largo, la cabecera se recorta para no salirse del margen.
- El PDF lleva metadatos de documento (título, autor y subtítulo).
- Al convertir varios ficheros, si uno falla se informa con `[ERROR: …]` y se
  continúa con el resto; el comando termina con código distinto de cero si hubo
  algún fallo.
- El tamaño de página es A4 por defecto, configurable con `page_size`,
  `orientation` y `margins` (ver arriba).
