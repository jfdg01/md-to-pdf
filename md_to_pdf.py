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
                            Operator, String, Token)
from pygments.util import ClassNotFound
import pypdf
import weasyprint

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
FONTS_DIR = SCRIPT_DIR / "fonts"
LOGO_NAMES = ["logo.webp", "logo.png", "logo.jpg", "logo_uja.webp", "logo_uja.png"]

# Tamaño de página A4 en pulgadas y márgenes del cuerpo.
PAGE_MARGIN = "1.15in 0.85in 0.95in 0.85in"

STRINGS = {
    "es": {
        "toc":         "Índice de contenidos",
        "idx_figures": "Índice de figuras",
        "idx_tables":  "Índice de tablas",
        "idx_code":    "Índice de bloques de código",
        "figure":      "Figura",
        "table":       "Tabla",
        "code_block":  "Bloque de código",
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
        "by":          "By",
    },
}


def get_strings(lang):
    return STRINGS.get((lang or "es").lower(), STRINGS["es"])


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

# Gama cálida: marrones suaves y naranjas, sobre un fondo crema tenue.
CODE_PALETTE = {
    "background": "#faf6f0",   # fondo del bloque, crema cálido
    "text":       "#4a3b2f",   # texto por defecto, marrón oscuro
    "comment":    "#a89580",   # comentarios, marrón claro apagado (cursiva)
    "keyword":    "#c25d1e",   # palabras clave (def, return, if…), naranja quemado
    "builtin":    "#b07d2b",   # funciones/constantes integradas, ámbar
    "name":       "#5a4636",   # identificadores, marrón medio
    "function":   "#a85420",   # nombres de función/clase, naranja terroso
    "string":     "#8a6d3b",   # cadenas de texto, tan tostado
    "number":     "#bf6a1f",   # números, naranja cálido
    "operator":   "#c25d1e",   # operadores (+, =, ->), naranja quemado
    "error":      "#b3402a",   # tokens erróneos, rojo-ladrillo
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
        formatter = HtmlFormatter(style=style, noclasses=True, cssclass="codehilite")
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

/* ── Mantener junto al elemento anterior (TODO #6) ──
   Evita el salto de página *antes* del elemento y permite que el propio
   elemento se parta si no cabe, de modo que quede pegado al texto previo. */
.keep-with-prev { break-before: avoid; break-inside: auto; }

/* Outline del PDF: solo las secciones del cuerpo, no la portada ni los índices. */
h1, h2, h3, h4, h5, h6 { bookmark-level: none; }
.body h2 { bookmark-level: 1; }
.body h3 { bookmark-level: 2; }
"""


def _css_str(s):
    """Escapa una cadena para incrustarla en un valor `content:` de CSS."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def page_css(meta, strings):
    """@page del cuerpo: márgenes + cabecera (título · subtítulo) y pie
    (autor centrado, 'n / total' a la derecha). El texto se incrusta como
    cadenas CSS; los recuadros de margen recortan lo que sobre."""
    header = " · ".join(filter(None, [meta.get("title", ""), meta.get("subtitle", "")]))
    author = meta.get("author", "")
    top = (f'content: "{_css_str(header)}";' if header else "content: none;")
    bottom = (f'content: "{_css_str(author)}";' if author else "content: none;")
    return f"""
@page {{
    size: A4;
    margin: {PAGE_MARGIN};
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
}


def parse_front_matter(text):
    """Lee un bloque de front matter YAML simple (`clave: valor`) delimitado por
    líneas `---` al principio del fichero (TODO #4). Devuelve (meta, body).

    Si no hay front matter, el cuerpo es el texto entero y el título se toma del
    primer encabezado `# ` (que se elimina del cuerpo para no duplicarlo)."""
    meta = {"title": "", "subtitle": "", "comment": "", "author": "",
            "logo": "", "lang": "es", "code_theme": ""}
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
    """Resuelve el logo/imagen de portada a un data URI. Prioriza el campo
    `logo:` del front matter (ruta arbitraria, TODO #3); si no, autodetecta
    un fichero logo.* junto al .md o al script. `logo: none` lo desactiva."""
    candidates = []
    logo_field = (meta.get("logo") or "").strip()
    if logo_field.lower() in ("none", "no", "false"):
        return None
    if logo_field:
        p = Path(logo_field)
        candidates = [p if p.is_absolute() else md_path.parent / p]
    else:
        for name in LOGO_NAMES:
            candidates += [md_path.parent / name, SCRIPT_DIR / name]

    for logo in candidates:
        if logo.exists():
            data = logo.read_bytes()
            mime = mimetypes.guess_type(logo.name)[0] or "image/png"
            return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return None


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

def cover_html(meta, logo_uri, strings):
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
<style>@page {{ size: A4; margin: 0; }}{font_face_css()}{BASE_CSS}</style>
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


def content_html(meta, body_md, strings, code_style=CUSTOM_CODE_STYLE):
    """Índice + índices + cuerpo en un único HTML. Lanza ValueError si algún
    elemento carece de descripción (TODO #7)."""
    md = markdown.Markdown(
        extensions=[TocExtension(toc_depth="2-3"), "tables", "fenced_code", "codehilite"],
        extension_configs={"codehilite": {
            "noclasses": True, "guess_lang": False, "pygments_style": code_style}},
    )
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
    body = apply_keep_with_prev(body)
    indices = _indices_html(figures, tables, code_blocks, strings)
    lang = meta.get("lang", "es")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8">
<style>{page_css(meta, strings)}{font_face_css()}{BASE_CSS}</style>
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

    html = content_html(meta, body_md, strings, code_style)
    content_pdf = weasyprint.HTML(string=html, base_url=base_url).write_pdf()
    cover_pdf = weasyprint.HTML(
        string=cover_html(meta, logo_uri, strings), base_url=base_url).write_pdf()

    pdf_bytes = merge_pdfs(cover_pdf, content_pdf, meta)
    pdf_path.write_bytes(pdf_bytes)
    return len(pdf_bytes)


def main():
    if len(sys.argv) > 1:
        md_files = [Path(p) for p in sys.argv[1:]]
    else:
        md_files = sorted(Path(".").glob("*.md"))

    if not md_files:
        print("No hay archivos .md")
        sys.exit(1)

    failures = 0
    for md_path in md_files:
        pdf_path = md_path.with_suffix(".pdf")
        print(f"  {md_path.name} → {pdf_path.name}", end=" ", flush=True)
        try:
            kb = convert_one(md_path) // 1024
            print(f"[OK, {kb} KB]")
        except Exception as e:
            failures += 1
            print(f"[ERROR: {e}]")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
