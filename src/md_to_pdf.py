#!/usr/bin/env python3
"""
MD → PDF, render puro en Python con WeasyPrint (sin navegador).

Uso: python3 md_to_pdf.py                 (convierte todos los .md del directorio)
     python3 md_to_pdf.py f1.md f2.md ...  (convierte los archivos indicados)

Genera, por cada .md, un PDF con portada + índice navegable + índices de
figuras/tablas/código + cuerpo, con cabecera/pie y marcadores (outline).
Requiere: weasyprint, python-markdown, pypdf (todo pip, sin Chrome).
"""
import base64
import io
import mimetypes
import re
import sys
import time
from html import escape
from pathlib import Path

import markdown
from markdown.extensions.toc import TocExtension
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.style import Style
from pygments.styles import get_style_by_name
from pygments.token import (Comment, Error, Generic, Keyword, Name, Number,
                            Operator, String, Text, Token)
from pygments.util import ClassNotFound
import pypdf
import weasyprint

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent            # raíz del repo (src/ cuelga de aquí)
ASSETS_DIR = ROOT_DIR / "assets"        # fuentes e imágenes empaquetadas
FONTS_DIR = ASSETS_DIR / "fonts"

# Tamaño y márgenes del cuerpo por defecto (TODO #5: ambos configurables desde el
# front matter). DEFAULT_MARGINS va por lado: top right bottom left.
PAGE_MARGIN = "1.15in 0.85in 0.95in 0.85in"
DEFAULT_MARGINS = ("1.15in", "0.85in", "0.95in", "0.85in")

# Tamaños de página admitidos (clave normalizada → palabra clave CSS de WeasyPrint).
PAGE_SIZES = {
    "a3": "A3", "a4": "A4", "a5": "A5",
    "b4": "B4", "b5": "B5",
    "letter": "letter", "carta": "letter",
    "legal": "legal", "oficio": "legal",
    "ledger": "ledger", "tabloid": "ledger",
}

STRINGS = {
    "es": {
        "toc":         "Índice de contenidos",
        "idx_figures": "Índice de figuras",
        "idx_tables":  "Índice de tablas",
        "idx_code":    "Índice de bloques de código",
        "figure":      "Figura",
        "table":       "Tabla",
        "code_block":  "Bloque de código",
        "references":  "Referencias",
        "no_date":     "s.f.",
        "by":          "Realizado por",
    },
    "en": {
        "toc":         "Table of contents",
        "idx_figures": "List of figures",
        "idx_tables":  "List of tables",
        "idx_code":    "List of code blocks",
        "figure":      "Figure",
        "table":       "Table",
        "code_block":  "Code block",
        "references":  "References",
        "no_date":     "n.d.",
        "by":          "By",
    },
}


def get_strings(lang):
    return STRINGS.get((lang or "es").lower(), STRINGS["es"])


def _truthy(val):
    """Interpreta un valor de front matter como booleano (true/false, sí/no…)."""
    return str(val).strip().lower() in ("true", "1", "yes", "si", "sí", "on")


# ─────────────────────────── Fuentes ───────────────────────────

def _face(family, rel, weight, style):
    path = FONTS_DIR / rel
    if not path.exists():
        return ""
    return (
        "@font-face {"
        f"font-family:'{family}';"
        f"src:url('{path.as_uri()}') format('truetype');"
        f"font-weight:{weight};font-style:{style};}}\n"
    )


def font_face_css():
    """Fuentes embebidas (estáticas, para evitar rarezas con variables en
    WeasyPrint). WeasyPrint sí respeta @font-face también en la cabecera/pie,
    así que ya no hace falta estampar nada por separado."""
    serif = "Source_Serif_4/static"
    grot = "Space_Grotesk/static"
    mono = "Space_Mono"
    rules = [
        _face("Source Serif 4", f"{serif}/SourceSerif4-Regular.ttf", 400, "normal"),
        _face("Source Serif 4", f"{serif}/SourceSerif4-Italic.ttf", 400, "italic"),
        _face("Source Serif 4", f"{serif}/SourceSerif4-Bold.ttf", 700, "normal"),
        _face("Source Serif 4", f"{serif}/SourceSerif4-BoldItalic.ttf", 700, "italic"),
        _face("Space Grotesk", f"{grot}/SpaceGrotesk-Regular.ttf", 400, "normal"),
        _face("Space Grotesk", f"{grot}/SpaceGrotesk-Medium.ttf", 500, "normal"),
        _face("Space Grotesk", f"{grot}/SpaceGrotesk-Bold.ttf", 700, "normal"),
        _face("Space Mono", f"{mono}/SpaceMono-Regular.ttf", 400, "normal"),
        _face("Space Mono", f"{mono}/SpaceMono-Italic.ttf", 400, "italic"),
        _face("Space Mono", f"{mono}/SpaceMono-Bold.ttf", 700, "normal"),
        _face("Space Mono", f"{mono}/SpaceMono-BoldItalic.ttf", 700, "italic"),
    ]
    return "".join(rules)


# ─────────────────────── Paleta de resaltado de código ───────────────────────
# Paleta personalizada editable: cambia estos colores a tu gusto. Se usa cuando
# el front matter lleva `code_theme: custom` (o no lleva ninguno). Para usar un
# tema de Pygments ya hecho, pon `code_theme: monokai` (dracula, github-dark,
# solarized-light, friendly, nord, gruvbox-dark, etc.).

# Gama oscura apagada: tonos desaturados sobre un fondo gris pizarra, con buen
# contraste pero sin colores chillones. Pensada para lectura cómoda en impreso.
CODE_PALETTE = {
    "background": "#21252b",   # fondo del bloque, gris pizarra oscuro
    "text":       "#c5cad3",   # texto por defecto, gris claro suave
    "comment":    "#6b7480",   # comentarios, gris medio apagado (cursiva)
    "keyword":    "#b48ead",   # palabras clave (def, return, if…), malva apagado
    "builtin":    "#81a1c1",   # funciones/constantes integradas, azul apagado
    "name":       "#c5cad3",   # identificadores, gris claro suave
    "function":   "#88c0d0",   # nombres de función/clase, cian apagado
    "string":     "#a3be8c",   # cadenas de texto, verde salvia apagado
    "number":     "#d08770",   # números, naranja terroso apagado
    "operator":   "#b48ead",   # operadores (+, =, ->), malva apagado
    "error":      "#bf616a",   # tokens erróneos, rojo apagado
}


def _build_custom_style(palette):
    """Crea una clase Style de Pygments a partir del dict CODE_PALETTE."""
    return type("CustomCodeStyle", (Style,), {
        "background_color": palette["background"],
        "styles": {
            Token:          palette["text"],
            Comment:        f"italic {palette['comment']}",
            Keyword:        f"bold {palette['keyword']}",
            Keyword.Constant: palette["builtin"],
            Name:           palette["name"],
            Name.Builtin:   palette["builtin"],
            Name.Function:  palette["function"],
            Name.Class:     f"bold {palette['function']}",
            Name.Decorator: palette["function"],
            String:         palette["string"],
            Number:         palette["number"],
            Operator:       palette["operator"],
            Generic.Error:  palette["error"],
            Error:          palette["error"],
        },
    })


CUSTOM_CODE_STYLE = _build_custom_style(CODE_PALETTE)


def _style_fg(style):
    """Color de texto por defecto de un tema de Pygments (`#rrggbb`). Se pasa
    como `prestyles` al HtmlFormatter: con `noclasses` Pygments solo colorea los
    tokens resaltados, así que el texto plano (bloques sin lenguaje o fragmentos
    no resaltados) heredaría el color oscuro del cuerpo y quedaría ilegible sobre
    fondos oscuros; este color base, fijado en el `<pre>`, lo evita."""
    color = style.style_for_token(Text).get("color")
    return f"#{color}" if color else "#1a1a1a"


def resolve_code_style(name):
    """Resuelve el campo `code_theme`: devuelve la clase Style personalizada si
    está vacío o vale 'custom'; en otro caso, el tema de Pygments con ese nombre.
    Si el nombre no existe, avisa y cae en la paleta personalizada."""
    name = (name or "").strip().lower()
    if name in ("", "custom", "default"):
        return CUSTOM_CODE_STYLE
    try:
        return get_style_by_name(name)
    except ClassNotFound:
        print(f"    (aviso: tema de código '{name}' desconocido; uso la paleta "
              f"personalizada)", file=sys.stderr)
        return CUSTOM_CODE_STYLE


# Bloque con tema propio: un comentario `<!-- code-theme: X -->` en la línea
# justo encima de la valla ```. Permite que distintos bloques del mismo
# documento usen paletas distintas, por encima del tema general del documento.
_THEMED_BLOCK_RE = re.compile(
    r'<!--\s*code-theme:\s*(?P<theme>[^>]*?)\s*-->[ \t]*\r?\n'
    r'```[ \t]*(?P<lang>[\w+#.-]*)[ \t]*\r?\n'
    r'(?P<code>.*?)\r?\n```[ \t]*$',
    re.DOTALL | re.MULTILINE,
)


def extract_themed_blocks(body_md):
    """Extrae los bloques marcados con `<!-- code-theme: X -->` y los resalta con
    ese tema concreto (en lugar del tema general del documento). Los reemplaza
    por un marcador de texto plano y devuelve (markdown_modificado, {marca: html})
    para reinyectar el HTML ya resaltado tras la conversión de Markdown."""
    blocks = {}

    def repl(m):
        lang = (m.group("lang") or "").strip() or "text"
        style = resolve_code_style(m.group("theme"))
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = TextLexer()
        formatter = HtmlFormatter(style=style, noclasses=True, cssclass="codehilite",
                                  prestyles=f"color:{_style_fg(style)}")
        token = f"CODEBLOCKTHEME{len(blocks)}MARKER"
        blocks[token] = highlight(m.group("code"), lexer, formatter)
        return f"\n\n{token}\n\n"

    return _THEMED_BLOCK_RE.sub(repl, body_md), blocks


# ─────────────────────────── CSS ───────────────────────────
# Tamaños subidos +1 pt respecto a la versión anterior (TODO #5), salvo la
# cabecera/pie, que se mantienen a 9.5 pt.

BASE_CSS = """
html, body {
    margin: 0;
    padding: 0;
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 14pt;
    line-height: 1.6;
    color: #1a1a1a;
}

/* ── Portada ── */
.cover {
    height: 100vh;
    box-sizing: border-box;
    padding: 2.5cm 2cm;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    text-align: center;
}
.cover .top {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.cover h1 {
    font-family: 'Space Grotesk', Arial, sans-serif;
    font-size: 27pt;
    font-weight: bold;
    border: none;
    margin: 0 0 20px 0;
    line-height: 1.3;
}
.cover .subtitle  { font-size: 16.5pt; font-style: italic; color: #444; margin: 0 0 6px 0; }
.cover .meta-line { font-size: 13pt; color: #555; margin: 3px 0; }
.cover .logo      { max-width: 180px; max-height: 180px; object-fit: contain; margin: 40px 0; }
.cover .author    { font-size: 14pt; font-style: italic; color: #333; padding-bottom: 1cm; }

/* ── Índice de contenidos ── */
.toc-page { break-after: page; font-family: 'Source Serif 4', Georgia, serif; }
.toc-page h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 18.5pt; margin-bottom: 20px; }
/* La fuente del índice (TODO #1): forzar la serif del documento en todos los
   elementos del árbol del TOC, evitando que herede una fuente del sistema. */
.toc-page .toc, .toc-page .toc * { font-family: 'Source Serif 4', Georgia, serif; }
.toc-page .toc { margin: 0; padding: 0; }
.toc-page .toc ul { list-style: none; margin: 0; padding: 0; }
.toc-page .toc li { padding: 5px 0; }
.toc-page .toc li li { padding-left: 2em; font-size: 13.5pt; font-weight: normal; }
.toc-page .toc > ul > li { font-size: 14.5pt; font-weight: bold; }
.toc-page .toc a { text-decoration: none; color: #1a1a1a; }

/* ── Índices de figuras/tablas/código ── */
.indices-section { break-after: page; font-family: 'Source Serif 4', Georgia, serif; }
.idx-block { margin-bottom: 32px; }
.idx-block h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 18.5pt; margin-bottom: 16px; }
.doc-index { list-style: none; margin: 0; padding: 0; }
.doc-index li { padding: 5px 0; border-bottom: 1px dotted #ddd; font-size: 14pt; }
.doc-index a { text-decoration: none; color: #1a1a1a; }
.idx-label { font-weight: bold; }

/* ── Contenido ── */
a { color: #5a8fc4; }
h1, h2, h3 { font-family: 'Space Grotesk', Arial, sans-serif; }
h1 { font-size: 24.5pt; margin-bottom: 16px; }
/* Cada sección de nivel ## empieza en página nueva. El salto forzado tras el
   índice y este se fusionan, así que no aparece una página en blanco. */
.body h2 { break-before: page; }
h2 { font-size: 18.5pt; margin-top: 28px; }
h3 { font-size: 15pt; margin-top: 20px; color: #222; }
code {
    font-family: 'Space Mono', 'DejaVu Sans Mono', monospace;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 12pt;
}
pre {
    font-family: 'Space Mono', 'DejaVu Sans Mono', monospace;
    background: #f4f4f4;
    border-radius: 4px;
    padding: 12px;
    font-size: 11.5pt;
    line-height: 1.4;
    break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
}
pre code { background: none; padding: 0; }
/* Bloques resaltados (codehilite con noclasses): el <div> lleva el color de
   fondo del tema en línea; hacemos que el <pre> interior sea transparente y
   pasamos el relleno/redondeo al <div>, para que también funcionen los temas
   oscuros (monokai, dracula…) sin que el fondo gris de `pre` los tape. */
.codehilite { background: #f4f4f4; border-radius: 4px; padding: 12px; break-inside: avoid; }
.codehilite pre { background: transparent; padding: 0; margin: 0; border-radius: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13pt; break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
th { background: #e8e8e8; font-weight: bold; }
blockquote {
    border-left: 4px solid #aaa;
    margin: 12px 0;
    padding: 4px 16px;
    color: #555;
    background: #fafafa;
}
hr { border: none; border-top: 1px solid #ccc; margin: 28px 0; }
ul, ol { margin: 6px 0; padding-left: 2em; }
li { margin: 0; }
li > p { margin: 0; padding: 0; }
figure { margin: 14px auto; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
figcaption { font-size: 12pt; color: #555; margin-top: 5px; font-style: italic; }
caption { caption-side: bottom; font-size: 12pt; color: #555; padding-top: 6px; font-style: italic; text-align: center; }
.code-block { margin: 12px 0; break-inside: avoid; }
.code-block > pre, .code-block > .codehilite { margin: 0; }
.code-label { font-size: 12pt; color: #555; margin: 4px 0 0; font-style: italic; text-align: center; }

/* ── Citas y bibliografía ── */
a.cite { text-decoration: none; }
.ref-entry {
    display: block;
    margin: 6px 0;
    padding-left: 1.6em;
    text-indent: -1.6em;   /* sangría francesa: la 1ª línea sobresale */
}

/* ── Mantener junto al elemento anterior (TODO #6) ──
   Evita el salto de página *antes* del elemento y permite que el propio
   elemento se parta si no cabe, de modo que quede pegado al texto previo.
   El `break-inside: auto` debe alcanzar también al `.codehilite`/`pre`
   interior: si no, un bloque más alto que una página deja la marca de "no
   romper dentro" intacta, vuelve irresoluble el "pegar al anterior" y
   WeasyPrint empuja el bloque hacia abajo dejando un hueco enorme. */
.keep-with-prev { break-before: avoid; }
.keep-with-prev,
.keep-with-prev .codehilite,
.keep-with-prev pre { break-inside: auto; }

/* Outline del PDF: solo las secciones del cuerpo, no la portada ni los índices. */
h1, h2, h3, h4, h5, h6 { bookmark-level: none; }
.body h2 { bookmark-level: 1; }
.body h3 { bookmark-level: 2; }
"""


def _css_str(s):
    """Escapa una cadena para incrustarla en un valor `content:` de CSS."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def resolve_page_size(meta):
    """Resuelve `page_size` + `orientation` a un valor CSS para `@page { size }`
    (p. ej. 'A4' o 'letter landscape'). Avisa y cae en el valor por defecto si el
    tamaño o la orientación son desconocidos (igual que con `code_theme`)."""
    name = (meta.get("page_size") or "").strip().lower()
    size = PAGE_SIZES.get(name, "A4") if name else "A4"
    if name and name not in PAGE_SIZES:
        print(f"    (aviso: tamaño de página '{name}' desconocido; uso A4)",
              file=sys.stderr)
    orient = (meta.get("orientation") or "").strip().lower()
    if orient in ("landscape", "apaisado", "horizontal"):
        return f"{size} landscape"
    if orient and orient not in ("portrait", "vertical", "retrato"):
        print(f"    (aviso: orientación '{orient}' desconocida; uso vertical)",
              file=sys.stderr)
    return size


def resolve_margins(meta):
    """Resuelve los márgenes del cuerpo a un valor CSS `top right bottom left`.
    Prioriza `margins` (CSS literal, p. ej. '1.15in 0.85in'); si no, compone con
    las claves por lado (`margin_top`…), usando el valor por defecto en las que
    falten."""
    whole = (meta.get("margins") or "").strip()
    if whole:
        return whole
    sides = ("margin_top", "margin_right", "margin_bottom", "margin_left")
    return " ".join((meta.get(k) or "").strip() or d
                    for k, d in zip(sides, DEFAULT_MARGINS))


def page_css(meta, strings, page_size):
    """@page del cuerpo: tamaño + márgenes + cabecera (título · subtítulo) y pie
    (autor centrado, 'n / total' a la derecha). El texto se incrusta como
    cadenas CSS; los recuadros de margen recortan lo que sobre."""
    header = " · ".join(filter(None, [meta.get("title", ""), meta.get("subtitle", "")]))
    author = meta.get("author", "")
    top = (f'content: "{_css_str(header)}";' if header else "content: none;")
    bottom = (f'content: "{_css_str(author)}";' if author else "content: none;")
    return f"""
@page {{
    size: {page_size};
    margin: {resolve_margins(meta)};
    @top-center {{
        {top}
        font-family: 'Space Grotesk', Arial, sans-serif;
        font-size: 9.5pt; color: #666;
        white-space: nowrap; overflow: hidden;
    }}
    @bottom-center {{
        {bottom}
        font-family: 'Space Grotesk', Arial, sans-serif;
        font-size: 9.5pt; color: #666;
        white-space: nowrap; overflow: hidden;
    }}
    @bottom-right {{
        content: counter(page) " / " counter(pages);
        font-family: 'Space Grotesk', Arial, sans-serif;
        font-size: 9.5pt; color: #666;
    }}
}}
"""


# ─────────────────────── Front matter / metadatos ───────────────────────

_META_ALIASES = {
    "title": "title", "titulo": "title", "título": "title",
    "subtitle": "subtitle", "subtitulo": "subtitle", "subtítulo": "subtitle",
    "comment": "comment", "comentario": "comment",
    "author": "author", "autor": "author",
    "logo": "logo", "image": "logo", "imagen": "logo",
    "locale": "lang", "language": "lang", "lang": "lang", "idioma": "lang",
    "code_theme": "code_theme", "code_style": "code_theme",
    "codetheme": "code_theme", "tema_codigo": "code_theme",
    "tema_código": "code_theme",
    "numbering": "numbering", "numeracion": "numbering",
    "numeración": "numbering", "numerar": "numbering",
    "page_size": "page_size", "pagesize": "page_size",
    "tamano": "page_size", "tamaño": "page_size",
    "tamano_pagina": "page_size", "tamaño_pagina": "page_size",
    "tamaño_página": "page_size",
    "orientation": "orientation", "orientacion": "orientation",
    "orientación": "orientation",
    "margins": "margins", "margenes": "margins", "márgenes": "margins",
    "margin": "margins", "margen": "margins",
    "margin_top": "margin_top", "margen_superior": "margin_top",
    "margin_right": "margin_right", "margen_derecho": "margin_right",
    "margin_bottom": "margin_bottom", "margen_inferior": "margin_bottom",
    "margin_left": "margin_left", "margen_izquierdo": "margin_left",
    "bibliography": "bibliography", "bibliografia": "bibliography",
    "bibliografía": "bibliography", "bib": "bibliography",
    "references": "bibliography", "referencias": "bibliography",
    "citation_style": "citation_style", "citationstyle": "citation_style",
    "cite_style": "citation_style", "estilo_cita": "citation_style",
    "estilo_citas": "citation_style", "estilo_de_cita": "citation_style",
}


def parse_front_matter(text):
    """Lee un bloque de front matter YAML simple (`clave: valor`) delimitado por
    líneas `---` al principio del fichero (TODO #4). Devuelve (meta, body).

    Si no hay front matter, el cuerpo es el texto entero y el título se toma del
    primer encabezado `# ` (que se elimina del cuerpo para no duplicarlo)."""
    meta = {"title": "", "subtitle": "", "comment": "", "author": "",
            "logo": "", "lang": "es", "code_theme": "", "numbering": "true",
            "page_size": "", "orientation": "", "margins": "",
            "margin_top": "", "margin_right": "", "margin_bottom": "",
            "margin_left": "", "bibliography": "", "citation_style": ""}
    lines = text.splitlines()
    body_start = 0

    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for raw in lines[1:i]:
                    if ":" not in raw:
                        continue
                    key, val = raw.split(":", 1)
                    canon = _META_ALIASES.get(key.strip().lower())
                    if canon:
                        meta[canon] = val.strip().strip('"').strip("'").strip()
                body_start = i + 1
                break

    body_lines = lines[body_start:]

    if not meta["title"]:
        for idx, line in enumerate(body_lines):
            if line.startswith("# "):
                meta["title"] = line[2:].strip()
                del body_lines[idx]
                break

    return meta, "\n".join(body_lines)


def find_logo(md_path, meta):
    """Resuelve el logo/imagen de portada a un data URI a partir del campo
    `logo:` del front matter (ruta arbitraria relativa al .md o absoluta).
    Si no se indica `logo:`, la portada no lleva imagen. `logo: none` también
    lo desactiva explícitamente."""
    logo_field = (meta.get("logo") or "").strip()
    if not logo_field or logo_field.lower() in ("none", "no", "false"):
        return None

    p = Path(logo_field)
    logo = p if p.is_absolute() else md_path.parent / p
    if logo.exists():
        data = logo.read_bytes()
        mime = mimetypes.guess_type(logo.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return None


# ─────────────────────── Numeración de secciones y referencias cruzadas ───────────────────────

_HEADING_RE = re.compile(r'^(#{2,6})\s+(.*)$')
_FENCE_RE = re.compile(r'^\s*(```|~~~)')


def apply_section_numbering(body_md):
    """Numera automáticamente los encabezados de sección (`##` → 1, 2, 3…) y
    subsección (`###` → 1.1, 1.2…) en el Markdown antes de convertirlo, de modo
    que el número aparezca igual en el cuerpo, en el índice de contenidos y en los
    marcadores (outline) del PDF, sin que el autor lo escriba a mano.

    Solo afecta a `##` y `###`; ignora los encabezados dentro de vallas de código.
    Activada por defecto; desactívala con `numbering: false` en el front matter si
    el documento ya trae la numeración escrita a mano (para no duplicarla)."""
    h2 = h3 = 0
    in_fence = False
    out = []
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        if m and len(m.group(1)) == 2:
            h2 += 1
            h3 = 0
            out.append(f"## {h2}. {m.group(2)}")
        elif m and len(m.group(1)) == 3:
            h3 += 1
            out.append(f"### {h2}.{h3} {m.group(2)}")
        else:
            out.append(line)
    return "\n".join(out)


# Referencia cruzada `[[fig-2-1]]` / `[[tab-1-1]]` / `[[code-3-2]]`: apunta a las
# anclas que genera add_asset_numbers. El patrón es estricto (tipo-x-y) para no
# capturar dobles corchetes que aparezcan por casualidad en el texto o el código.
_XREF_RE = re.compile(r'\[\[\s*((?:fig|tab|code)-\d+-\d+)\s*\]\]')


def resolve_cross_refs(html, figures, tables, code_blocks):
    """Resuelve las referencias cruzadas `[[fig-2-1]]` a un enlace al ancla del
    elemento, mostrando su número como texto visible (p. ej. «Figura 2.1»). Avisa
    de las referencias a anclas inexistentes y las deja sin tocar para que el
    autor las localice (igual que con un `code_theme` desconocido)."""
    labels = {aid: nl for nl, cap, aid in (*figures, *tables, *code_blocks)}

    def repl(m):
        aid = m.group(1)
        label = labels.get(aid)
        if not label:
            print(f"    (aviso: referencia cruzada a '{aid}' inexistente)",
                  file=sys.stderr)
            return m.group(0)
        return f'<a href="#{aid}" class="xref">{escape(label)}</a>'

    return _XREF_RE.sub(repl, html)


# ─────────────────────── Bibliografía y citas ───────────────────────
# Cita en el cuerpo: `[@clave]` o varias juntas `[@clave1; @clave2]`. Cada clave
# se sustituye por una marca enlazada (numérica `[1]` o autor-año `(Pérez, 2020)`)
# que salta a su entrada en la sección de referencias, generada con las entradas
# realmente citadas. La bibliografía se lee de un `.bib` (BibTeX) indicado en el
# front matter con `bibliography:` (ruta relativa al .md, como `logo`).
_CITE_GROUP_RE = re.compile(r'\[@[^\]]+\]')
_CITE_KEY_RE = re.compile(r'@([\w:.\-]+)')
_INLINE_CODE_RE = re.compile(r'`+[^`]*`+')

# Estilos de cita admitidos (clave normalizada → estilo canónico).
_CITE_STYLES = {
    "": "numeric", "numeric": "numeric", "numerico": "numeric",
    "numérico": "numeric", "numerica": "numeric", "numérica": "numeric",
    "number": "numeric", "numero": "numeric",
    "author-year": "author-year", "author_year": "author-year",
    "authoryear": "author-year", "autor-año": "author-year",
    "autor-ano": "author-year", "autor_año": "author-year",
    "autor-anyo": "author-year", "autoraño": "author-year",
}


def resolve_citation_style(meta):
    """Resuelve `citation_style`: 'numeric' (def.) o 'author-year'. Avisa y cae en
    'numeric' si el valor es desconocido (igual que con `code_theme`)."""
    name = (meta.get("citation_style") or "").strip().lower()
    if name in _CITE_STYLES:
        return _CITE_STYLES[name]
    print(f"    (aviso: estilo de cita '{name}' desconocido; uso numeric)",
          file=sys.stderr)
    return "numeric"


def load_bibliography(md_path, meta):
    """Carga el `.bib` indicado en `bibliography:` (ruta relativa al .md, como el
    logo) y devuelve sus entradas (dict clave→entrada de pybtex, insensible a
    mayúsculas). Sin campo `bibliography`, devuelve {} (no hay bibliografía).
    Lanza ValueError si el fichero no existe o falta pybtex."""
    field = (meta.get("bibliography") or "").strip()
    if not field:
        return {}
    p = Path(field)
    bib_path = p if p.is_absolute() else md_path.parent / p
    if not bib_path.exists():
        raise ValueError(f"no encuentro la bibliografía '{field}'")
    try:
        from pybtex.database import parse_file
    except ImportError:
        raise ValueError("la bibliografía necesita 'pybtex' (instálalo con: uv sync)")
    return parse_file(str(bib_path)).entries


def _ref_anchor(key):
    """Ancla estable para una entrada de la bibliografía (`ref-<clave>`)."""
    return "ref-" + re.sub(r'[^a-z0-9]+', '-', key.lower()).strip('-')


def _clean(value):
    """Texto plano de un campo BibTeX: quita llaves y espacios sobrantes."""
    return str(value).replace("{", "").replace("}", "").strip()


def _persons(entry):
    return entry.persons.get("author") or entry.persons.get("editor") or []


def _person_last(p):
    return _clean(" ".join(p.prelast_names + p.last_names))


def _person_full(p):
    """Apellido(s) + iniciales: «Pérez, J. M.»."""
    last = _person_last(p)
    initials = " ".join(f"{_clean(n)[0]}." for n in (p.first_names + p.middle_names)
                        if _clean(n))
    if last and initials:
        return f"{last}, {initials}"
    return last or initials


def _entry_year(entry, strings):
    return _clean(entry.fields.get("year", "")) or strings["no_date"]


def _authors_full(entry, lang):
    """Lista de autores para la entrada de referencias («A, B y C»)."""
    names = [_person_full(p) for p in _persons(entry)]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    conn = " y " if lang == "es" else " & "
    return ", ".join(names[:-1]) + conn + names[-1]


def _authors_short(entry, lang):
    """Apellidos abreviados para la marca autor-año («Pérez», «Pérez et al.»)."""
    lasts = [_person_last(p) for p in _persons(entry)]
    if not lasts:
        return _clean(entry.fields.get("title", "")) or "?"
    if len(lasts) == 1:
        return lasts[0]
    if len(lasts) == 2:
        conn = " y " if lang == "es" else " & "
        return lasts[0] + conn + lasts[1]
    return f"{lasts[0]} et al."


def _format_reference(entry, lang, strings):
    """Entrada formateada de forma consistente: «Autores (año). *Título*. Soporte.»"""
    fields = entry.fields
    title = _clean(fields.get("title", ""))
    container = _clean(fields.get("journal") or fields.get("booktitle")
                       or fields.get("publisher") or fields.get("school")
                       or fields.get("institution") or "")
    authors = _authors_full(entry, lang)
    parts = [f"{authors} ({_entry_year(entry, strings)})." if authors
             else f"({_entry_year(entry, strings)})."]
    if title:
        parts.append(f"*{title}*.")
    if container:
        parts.append(f"{container}.")
    return " ".join(parts)


def process_citations(body_md, bib_entries, style, lang, strings):
    """Sustituye las citas `[@clave]` del cuerpo por marcas enlazadas y construye
    la sección de referencias con las entradas citadas. Devuelve
    (markdown_con_marcas, markdown_referencias|None).

    Numera las claves por orden de primera aparición. Las marcas saltan al ancla
    `ref-<clave>` de la entrada (mecanismo de anclas del TODO #4). Avisa de las
    claves ausentes en el `.bib` y deja `@clave` visible. Ignora las citas dentro
    de vallas de código."""
    cited = []            # claves citadas, en orden de primera aparición
    number = {}           # clave (minúsculas) → número

    def number_for(key):
        k = key.lower()
        if k not in number:
            cited.append(key)
            number[k] = len(cited)
        return number[k]

    def render_group(m):
        parts = []
        for key in _CITE_KEY_RE.findall(m.group(0)):
            if key not in bib_entries:
                print(f"    (aviso: cita '@{key}' no está en la bibliografía)",
                      file=sys.stderr)
                parts.append(escape(f"@{key}"))
                continue
            num = number_for(key)
            if style == "author-year":
                label = f"{_authors_short(bib_entries[key], lang)}, " \
                        f"{_entry_year(bib_entries[key], strings)}"
            else:
                label = str(num)
            parts.append(f'<a href="#{_ref_anchor(key)}" class="cite">'
                         f'{escape(label)}</a>')
        if style == "author-year":
            return "(" + "; ".join(parts) + ")"
        return "[" + ", ".join(parts) + "]"

    def sub_line(line):
        # Sustituye fuera de los spans de código en línea (`...`), para no tocar
        # un `[@clave]` escrito como ejemplo entre acentos graves.
        parts, last = [], 0
        for m in _INLINE_CODE_RE.finditer(line):
            parts.append(_CITE_GROUP_RE.sub(render_group, line[last:m.start()]))
            parts.append(m.group(0))
            last = m.end()
        parts.append(_CITE_GROUP_RE.sub(render_group, line[last:]))
        return "".join(parts)

    out, in_fence = [], False
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
        elif in_fence:
            out.append(line)
        else:
            out.append(sub_line(line))
    new_body = "\n".join(out)

    if not cited:
        return new_body, None

    # Orden de la lista: por número de cita (numeric) o alfabético por autor
    # (author-year). Cada entrada lleva su ancla `ref-<clave>`.
    if style == "author-year":
        ordered = sorted(cited, key=lambda k: (
            _person_last(_persons(bib_entries[k])[0]).lower()
            if _persons(bib_entries[k])
            else _clean(bib_entries[k].fields.get("title", "")).lower(),
            _entry_year(bib_entries[k], strings)))
    else:
        ordered = cited

    lines = [f'## {strings["references"]}', ""]
    for key in ordered:
        marker = "" if style == "author-year" else f'[{number[key.lower()]}] '
        text = _format_reference(bib_entries[key], lang, strings)
        lines.append(f'<span id="{_ref_anchor(key)}" class="ref-entry">'
                     f'{marker}{text}</span>')
        lines.append("")
    return new_body, "\n".join(lines)


# ─────────────────────── Numeración de figuras/tablas/código ───────────────────────

def add_asset_numbers(html, strings):
    """Numera figuras, tablas y bloques de código (x.y, reiniciando en cada
    `<h2>`), añade su etiqueta y recoge los datos para los índices.

    Devuelve (html, figures, tables, code_blocks, missing). `missing` lista las
    etiquetas de los elementos SIN descripción: la imagen usa su `alt`; tablas y
    bloques de código requieren `<!-- caption: -->`. Si `missing` no está vacío,
    el llamador rechaza generar el PDF (TODO #7)."""
    section = [0]
    figs = [0]
    tabs = [0]
    codes = [0]
    pending_cap = [""]
    figures, tables, code_blocks, missing = [], [], [], []
    pattern = re.compile(
        r'<!--\s*caption:\s*(.*?)\s*-->'
        r'|<h2\b[^>]*>|<img\b[^>]*/?>|<table\b[^>]*>'
        r'|<div[^>]*\bclass="codehilite"[^>]*>.*?</div>'
        r'|<pre\b[^>]*>.*?</pre>',
        re.DOTALL,
    )

    def _full_label(num_label, caption):
        return f"{num_label}: {caption}" if caption else num_label

    def sub(m):
        tag = m.group(0)
        lo = tag.lower()
        if lo.startswith('<!--'):
            cap_m = re.match(r'<!--\s*caption:\s*(.*?)\s*-->', tag, re.DOTALL)
            pending_cap[0] = cap_m.group(1).strip() if cap_m else ""
            return ""   # quita el comentario de la salida
        if lo.startswith('<h2'):
            section[0] += 1
            figs[0] = tabs[0] = codes[0] = 0
            pending_cap[0] = ""
            return tag
        if lo.startswith('<img'):
            if not section[0]:
                return tag
            figs[0] += 1
            num_label = f"{strings['figure']} {section[0]}.{figs[0]}"
            fig_id = f"fig-{section[0]}-{figs[0]}"
            alt_m = re.search(r'\balt="([^"]*)"', tag)
            alt = alt_m.group(1) if alt_m else ""
            caption = pending_cap[0] or alt
            pending_cap[0] = ""
            if not caption:
                missing.append(num_label)
            figures.append((num_label, caption, fig_id))
            rendered = escape(_full_label(num_label, caption))
            return f'<figure id="{fig_id}">{tag}<figcaption>{rendered}</figcaption></figure>'
        if lo.startswith('<table'):
            if not section[0]:
                return tag
            tabs[0] += 1
            num_label = f"{strings['table']} {section[0]}.{tabs[0]}"
            tab_id = f"tab-{section[0]}-{tabs[0]}"
            caption = pending_cap[0]
            pending_cap[0] = ""
            if not caption:
                missing.append(num_label)
            tables.append((num_label, caption, tab_id))
            rendered = escape(_full_label(num_label, caption))
            return tag[:-1] + f' id="{tab_id}"><caption>{rendered}</caption>'
        if lo.startswith('<div') or lo.startswith('<pre'):
            if not section[0]:
                return tag
            codes[0] += 1
            num_label = f"{strings['code_block']} {section[0]}.{codes[0]}"
            code_id = f"code-{section[0]}-{codes[0]}"
            caption = pending_cap[0]
            pending_cap[0] = ""
            if not caption:
                missing.append(num_label)
            code_blocks.append((num_label, caption, code_id))
            rendered = escape(_full_label(num_label, caption))
            return (
                f'<div class="code-block" id="{code_id}">{tag}'
                f'<p class="code-label">{rendered}</p></div>'
            )
        return tag

    return pattern.sub(sub, html), figures, tables, code_blocks, missing


def apply_keep_with_prev(html):
    """Aplica la marca `<!-- keep -->` (TODO #6): añade la clase keep-with-prev
    al siguiente elemento de bloque, forzándolo a quedarse en la misma página
    que el contenido anterior. Se ejecuta tras la numeración, para que la marca
    afecte al envoltorio <figure>/<div class="code-block"> ya creado."""
    def inject(tag):
        cm = re.search(r'class="([^"]*)"', tag)
        if cm:
            return tag[:cm.start(1)] + (cm.group(1) + " keep-with-prev") + tag[cm.end(1):]
        return re.sub(r'^(<\w+)', r'\1 class="keep-with-prev"', tag, count=1)

    pattern = re.compile(
        r'<!--\s*keep(?:-with-(?:prev|previous))?\s*-->\s*(<[A-Za-z][^>]*>)',
        re.DOTALL,
    )
    return pattern.sub(lambda m: inject(m.group(1)), html)


def _indices_html(figures, tables, code_blocks, strings):
    """Construye la sección de índices (figuras/tablas/código) no vacíos."""
    def _block(title, rows):
        items = "\n".join(f'    <li>{r}</li>' for r in rows)
        return (
            f'<div class="idx-block">\n  <h2>{title}</h2>\n'
            f'  <ul class="doc-index">\n{items}\n  </ul>\n</div>\n'
        )

    def _row(num_label, caption, anchor_id):
        cap = f": {escape(caption)}" if caption else ""
        return (f'<a href="#{anchor_id}">'
                f'<span class="idx-label">{escape(num_label)}</span>{cap}</a>')

    parts = []
    for items, key in ((figures, "idx_figures"), (tables, "idx_tables"),
                       (code_blocks, "idx_code")):
        if items:
            rows = [_row(nl, cap, aid) for nl, cap, aid in items]
            parts.append(_block(strings[key], rows))
    if not parts:
        return ""
    return f'<div class="indices-section">\n{"".join(parts)}</div>\n'


# ─────────────────────────── HTML (portada y contenido) ───────────────────────────

def cover_html(meta, logo_uri, strings, page_size):
    title = escape(meta["title"])
    subtitle = escape(meta["subtitle"])
    comment = escape(meta["comment"])
    author = escape(meta["author"])
    lang = meta.get("lang", "es")
    logo_tag = f'<img class="logo" src="{logo_uri}" alt="">' if logo_uri else ""
    subtitle_tag = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    comment_tag = f'<p class="meta-line">{comment}</p>' if comment else ""
    author_tag = (f'<p class="author">{escape(strings["by"])} {author}</p>'
                  if author else "")
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8">
<style>@page {{ size: {page_size}; margin: 0; }}{font_face_css()}{BASE_CSS}</style>
</head>
<body>
<div class="cover">
  <div class="top">
    <h1>{title}</h1>
    {subtitle_tag}
    {comment_tag}
    {logo_tag}
  </div>
  {author_tag}
</div>
</body>
</html>"""


def content_html(meta, body_md, strings, code_style, page_size,
                 bib_entries=None, citation_style="numeric"):
    """Índice + índices + cuerpo en un único HTML. Lanza ValueError si algún
    elemento carece de descripción (TODO #7)."""
    md = markdown.Markdown(
        extensions=[TocExtension(toc_depth="2-3"), "tables", "fenced_code", "codehilite"],
        extension_configs={"codehilite": {
            "noclasses": True, "guess_lang": False, "pygments_style": code_style,
            "prestyles": f"color:{_style_fg(code_style)}"}},
    )
    # Citas y bibliografía: se procesan antes de numerar para que la sección de
    # «Referencias» (un `##` más) entre en la numeración, el índice y el outline.
    if bib_entries:
        body_md, refs_md = process_citations(
            body_md, bib_entries, citation_style, meta.get("lang", "es"), strings)
        if refs_md:
            body_md = f"{body_md}\n\n{refs_md}"
    # Numeración automática de secciones (activada por defecto): se aplica al
    # Markdown antes de convertir, para que el número quede reflejado en cuerpo,
    # índice y outline. Se desactiva con `numbering: false`.
    if _truthy(meta.get("numbering")):
        body_md = apply_section_numbering(body_md)
    # Los bloques con tema propio se resaltan aparte y se reinyectan tras la
    # conversión; el resto usa el tema general (code_style) vía codehilite.
    body_md, themed_blocks = extract_themed_blocks(body_md)
    body = md.convert(body_md)
    toc_tree = md.toc
    for token, snippet in themed_blocks.items():
        body = body.replace(f"<p>{token}</p>", snippet).replace(token, snippet)

    body, figures, tables, code_blocks, missing = add_asset_numbers(body, strings)
    if missing:
        raise ValueError(
            "elementos sin descripción (añade <!-- caption: ... --> o un alt): "
            + ", ".join(missing)
        )
    body = resolve_cross_refs(body, figures, tables, code_blocks)
    body = apply_keep_with_prev(body)
    indices = _indices_html(figures, tables, code_blocks, strings)
    lang = meta.get("lang", "es")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8">
<style>{page_css(meta, strings, page_size)}{font_face_css()}{BASE_CSS}</style>
</head>
<body>
<div class="toc-page">
  <h2>{strings["toc"]}</h2>
  {toc_tree}
</div>
{indices}<main class="body">{body}</main>
</body>
</html>"""


# ─────────────────────────── Ensamblado ───────────────────────────

def merge_pdfs(cover_bytes, content_bytes, meta):
    """Antepone la portada al contenido conservando outline y enlaces internos
    (pypdf reajusta las páginas), y escribe los metadatos del documento."""
    writer = pypdf.PdfWriter()
    writer.append(io.BytesIO(cover_bytes))
    writer.append(io.BytesIO(content_bytes))

    info = {tag: val for tag, val in (
        ("/Title", meta.get("title")),
        ("/Author", meta.get("author")),
        ("/Subject", meta.get("subtitle")),
    ) if val}
    if info:
        try:
            writer.add_metadata(info)
        except Exception:
            pass

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def convert_one(md_path):
    """Convierte un único .md a .pdf junto a él. Lanza excepción si algo falla."""
    pdf_path = md_path.with_suffix(".pdf")
    md_text = md_path.read_text(encoding="utf-8")
    meta, body_md = parse_front_matter(md_text)
    strings = get_strings(meta["lang"])
    logo_uri = find_logo(md_path, meta)
    base_url = md_path.resolve().parent.as_uri() + "/"
    code_style = resolve_code_style(meta.get("code_theme"))
    page_size = resolve_page_size(meta)
    bib_entries = load_bibliography(md_path, meta)
    citation_style = resolve_citation_style(meta) if bib_entries else "numeric"

    html = content_html(meta, body_md, strings, code_style, page_size,
                        bib_entries, citation_style)
    content_pdf = weasyprint.HTML(string=html, base_url=base_url).write_pdf()
    cover_pdf = weasyprint.HTML(
        string=cover_html(meta, logo_uri, strings, page_size),
        base_url=base_url).write_pdf()

    pdf_bytes = merge_pdfs(cover_pdf, content_pdf, meta)
    pdf_path.write_bytes(pdf_bytes)
    return len(pdf_bytes)


def convert_and_report(md_path):
    """Convierte un .md informando con el formato estándar
    (`nombre.md → nombre.pdf [OK, NN KB]` / `[ERROR: …]`). Devuelve True si fue
    bien. Lo usan tanto la conversión única como el modo --watch."""
    pdf_path = md_path.with_suffix(".pdf")
    print(f"  {md_path.name} → {pdf_path.name}", end=" ", flush=True)
    try:
        kb = convert_one(md_path) // 1024
        print(f"[OK, {kb} KB]")
        return True
    except Exception as e:
        print(f"[ERROR: {e}]")
        return False


def watch_files(md_files, watch_all):
    """Vigila los .md y regenera su PDF cada vez que se guardan (TODO #10). Con
    `watch_all` (sin archivos en la línea de órdenes) vigila todos los .md del
    directorio actual, incluidos los que se creen después. Aplica un pequeño
    debounce para no regenerar dos veces ante varios eventos de guardado seguidos,
    y sale limpiamente con Ctrl-C."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("El modo --watch necesita 'watchdog' (instálalo con: uv sync)")
        sys.exit(1)

    import threading

    # Rutas absolutas vigiladas → Path a convertir. En modo watch_all crece con
    # los .md nuevos que aparezcan en el directorio.
    targets = {p.resolve(): p for p in md_files}
    dirs = sorted({p.resolve().parent for p in md_files}) or [Path(".").resolve()]

    debounce = 0.3
    timers = {}
    lock = threading.Lock()

    def regenerate(path):
        with lock:
            timers.pop(path, None)
        convert_and_report(targets[path])

    def schedule(path):
        with lock:
            if path in timers:
                timers[path].cancel()
            timers[path] = threading.Timer(debounce, regenerate, args=[path])
            timers[path].start()

    def target_for(src_path):
        p = Path(src_path).resolve()
        if p.suffix != ".md":
            return None
        if p in targets:
            return p
        if watch_all:
            targets[p] = p   # convertir usando la ruta absoluta
            return p
        return None

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory and target_for(event.src_path):
                schedule(Path(event.src_path).resolve())

        on_created = on_modified

        def on_moved(self, event):
            # Algunos editores guardan moviendo un temporal sobre el fichero.
            dest = getattr(event, "dest_path", "")
            if dest and target_for(dest):
                schedule(Path(dest).resolve())

    observer = Observer()
    for d in dirs:
        observer.schedule(Handler(), str(d), recursive=False)
    observer.start()

    # Conversión inicial para dejar los PDF al día al arrancar.
    for md_path in md_files:
        convert_and_report(md_path)
    print(f"Vigilando {'el directorio actual' if watch_all else f'{len(targets)} archivo(s)'}"
          f". Pulsa Ctrl-C para salir.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSaliendo del modo --watch.")
    finally:
        with lock:
            for t in timers.values():
                t.cancel()
        observer.stop()
        observer.join()


def main():
    watch = False
    files = []
    for arg in sys.argv[1:]:
        if arg in ("--watch", "-w"):
            watch = True
        else:
            files.append(arg)

    watch_all = not files
    if files:
        md_files = [Path(p) for p in files]
    else:
        md_files = sorted(Path(".").glob("*.md"))

    if watch:
        watch_files(md_files, watch_all)
        return

    if not md_files:
        print("No hay archivos .md")
        sys.exit(1)

    failures = sum(not convert_and_report(p) for p in md_files)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
