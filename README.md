# md-to-pdf

Convierte ficheros Markdown en un PDF con **portada**, **índice navegable**,
**índices de figuras/tablas/código** y **cabecera/pie** en cada página. Sirve para
informes, manuales, apuntes o cualquier documento estructurado.

El render lo hace **WeasyPrint** (Python puro, sin navegador): rápido, ligero y
con el mismo resultado en cualquier máquina. Las fuentes (Source Serif 4, Space
Grotesk, Space Mono) viajan con el repositorio en `fonts/`.

---

## Requisitos

- **Python 3** (3.10+).
- Las librerías de sistema de WeasyPrint (Pango/Cairo). En Ubuntu/Debian:
  ```bash
  sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0
  ```
  En Windows se instalan con WeasyPrint según su documentación (GTK runtime).

Las dependencias de Python (`markdown`, `weasyprint`, `pypdf`, `watchdog`) se
instalan en un entorno virtual propio (`.venv/`) por el script de instalación.

---

## Instalación

El instalador crea el `.venv`, instala dependencias y registra el comando global
`md-to-pdf`.

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

# Sin argumentos: convierte TODOS los .md del directorio actual
md-to-pdf
```

Cada PDF se escribe junto a su `.md` de origen, con el mismo nombre.

### Modo vigilancia (`--watch`)

Con `--watch`, el conversor se queda observando y **regenera el PDF cada vez que
guardas** el `.md`, con el mismo formato de salida que la conversión única:

```bash
# Vigila TODOS los .md del directorio actual (incluidos los que crees después)
md-to-pdf --watch

# Vigila solo un fichero
md-to-pdf --watch informe.md
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

## 1. Introducción

Texto de la primera sección...

### 1.1 Un subapartado

Más texto...

## 2. Siguiente sección

...
```

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
| `numbering`| `true` numera solo las secciones automáticamente (def. `false`) | Secciones + índice |
| `page_size`| Tamaño de página: `a4` (def.), `a5`, `a3`, `letter`, `legal`… | Todo el documento |
| `orientation`| `portrait` (def.) o `landscape`                         | Todo el documento |
| `margins`  | Márgenes del cuerpo en CSS (`1.15in 0.85in 0.95in 0.85in`) | Todo el documento |

Se aceptan alias en español (`titulo`, `subtitulo`, `autor`, `imagen`, `idioma`,
`numeracion`, `tamaño`, `orientacion`, `margenes`…).
Si no defines `title`, se usa el primer encabezado `# ` del cuerpo. Si no defines
`logo` pero existe un `logo.*` junto al `.md`, se usa automáticamente; con
`logo: none` lo desactivas.

### Reglas del cuerpo

- **`## ` = sección.** Cada encabezado de nivel 2 empieza en una **página nueva**.
  Numéralas `## 1. ...`, `## 2. ...` a mano, o activa `numbering: true` (abajo).
- **`### ` = subsección.** No fuerza salto de página.
- **El índice** lista automáticamente los `##` y `###`, con enlaces que saltan a
  la sección al hacer clic, y el PDF incluye **marcadores** con esa jerarquía.
- Funciona el Markdown habitual: **negrita**, *cursiva*, listas, tablas, `código`
  en línea y bloques con triple acento grave, citas.

### Numeración automática de secciones

Con `numbering: true` en el front matter, el conversor numera las secciones por
ti: los `##` reciben `1.`, `2.`, `3.`… y los `###` su `1.1`, `1.2`… El número
aparece igual en el cuerpo, en el índice de contenidos y en los marcadores del
PDF, así que **no lo escribas a mano** en los encabezados (def. `false`, para no
duplicar la numeración de los documentos que ya la traen escrita).

### Referencias cruzadas

Para enlazar a una figura, tabla o bloque de código por su número, escribe su
ancla entre dobles corchetes: `[[fig-2-1]]`, `[[tab-2-1]]` o `[[code-2-1]]` (el
formato es `tipo-sección-índice`, las mismas anclas que se numeran solas). Se
convierte en un enlace cuyo texto visible es el número del elemento («Figura
2.1») y que salta a él al hacer clic. Si el ancla no existe, se avisa por consola
y la marca se deja tal cual para que la localices.

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
  con acentos desaturados) definida en `md_to_pdf.py`. Es el valor por defecto.
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
principio de `md_to_pdf.py`: cada clave (`keyword`, `string`, `comment`,
`function`, `number`, `background`…) es un color hex que puedes cambiar a tu
gusto. Los temas oscuros funcionan porque el `<pre>` interior es transparente y
el fondo lo pinta el contenedor con el color del tema.

---

## Notas

- Cabecera, pie, portada y cuerpo usan las fuentes incrustadas en `fonts/`, así
  que el resultado es idéntico en cualquier sistema sin instalar nada. Si el
  título es muy largo, la cabecera se recorta para no salirse del margen.
- El PDF lleva metadatos de documento (título, autor y subtítulo).
- Al convertir varios ficheros, si uno falla se informa con `[ERROR: …]` y se
  continúa con el resto; el comando termina con código distinto de cero si hubo
  algún fallo.
- El tamaño de página es A4 por defecto, configurable con `page_size`,
  `orientation` y `margins` (ver arriba).
