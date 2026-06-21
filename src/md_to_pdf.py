#!/usr/bin/env python3
"""
MD -> PDF, pure-Python rendering with WeasyPrint (no browser).

Usage: python3 md_to_pdf.py file.md ...   (converts the given files)
       python3 md_to_pdf.py directory/    (converts every .md in the directory)

For each .md it builds a PDF with a cover + navigable table of contents +
lists of figures/tables/code blocks + body, with a running header/footer and
bookmarks (outline).
Requires: weasyprint, python-markdown, pypdf (all pip, no Chrome).
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
ROOT_DIR = SCRIPT_DIR.parent            # repo root (src/ hangs off this)
ASSETS_DIR = ROOT_DIR / "assets"        # bundled fonts and images
FONTS_DIR = ASSETS_DIR / "fonts"

# Default body margins, per side: top right bottom left.
DEFAULT_MARGINS = ("1.15in", "0.85in", "0.95in", "0.85in")

# Supported page sizes (normalized key -> WeasyPrint CSS keyword).
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
    """Interpret a front-matter value as a boolean (true/false, yes/no…)."""
    return str(val).strip().lower() in ("true", "1", "yes", "si", "sí", "on")


# ─────────────────────────── Fonts ───────────────────────────

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
    """Embedded fonts (static, to avoid quirks with variable fonts in
    WeasyPrint). WeasyPrint honours @font-face in the header/footer too, so
    nothing needs to be stamped separately."""
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


# ─────────────────────── Code-highlight palette ───────────────────────
# Editable custom palette: change these colors to taste. Used when the front
# matter has `code_theme: custom` (or none at all). To use a ready-made Pygments
# theme, set `code_theme: monokai` (dracula, github-dark, solarized-light,
# friendly, nord, gruvbox-dark, etc.).

# Muted dark range: desaturated tones on a slate-grey background, good contrast
# without garish colors. Designed for comfortable reading in print.
CODE_PALETTE = {
    "background": "#21252b",   # block background, dark slate grey
    "text":       "#c5cad3",   # default text, soft light grey
    "comment":    "#6b7480",   # comments, muted medium grey (italic)
    "keyword":    "#b48ead",   # keywords (def, return, if…), muted mauve
    "builtin":    "#81a1c1",   # builtin functions/constants, muted blue
    "name":       "#c5cad3",   # identifiers, soft light grey
    "function":   "#88c0d0",   # function/class names, muted cyan
    "string":     "#a3be8c",   # string literals, muted sage green
    "number":     "#d08770",   # numbers, muted earthy orange
    "operator":   "#b48ead",   # operators (+, =, ->), muted mauve
    "error":      "#bf616a",   # error tokens, muted red
}


def _build_custom_style(palette):
    """Build a Pygments Style class from the CODE_PALETTE dict."""
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
    """Default text color of a Pygments theme (`#rrggbb`). Passed as `prestyles`
    to the HtmlFormatter: with `noclasses`, Pygments only colors highlighted
    tokens, so plain text (blocks with no language or unhighlighted fragments)
    would inherit the body's dark color and become unreadable on dark
    backgrounds; this base color, set on the `<pre>`, prevents that."""
    color = style.style_for_token(Text).get("color")
    return f"#{color}" if color else "#1a1a1a"


def resolve_code_style(name):
    """Resolve the `code_theme` field: return the custom Style class if it is
    empty or equal to 'custom'; otherwise the Pygments theme with that name. If
    the name does not exist, warn and fall back to the custom palette."""
    name = (name or "").strip().lower()
    if name in ("", "custom", "default"):
        return CUSTOM_CODE_STYLE
    try:
        return get_style_by_name(name)
    except ClassNotFound:
        print(f"    (warning: unknown code theme '{name}'; using the custom "
              f"palette)", file=sys.stderr)
        return CUSTOM_CODE_STYLE


# Per-block theme: a `<!-- code-theme: X -->` comment on the line right above the
# ``` fence. Lets different blocks in the same document use different palettes,
# overriding the document-wide theme.
_THEMED_BLOCK_RE = re.compile(
    r'<!--\s*code-theme:\s*(?P<theme>[^>]*?)\s*-->[ \t]*\r?\n'
    r'```[ \t]*(?P<lang>[\w+#.-]*)[ \t]*\r?\n'
    r'(?P<code>.*?)\r?\n```[ \t]*$',
    re.DOTALL | re.MULTILINE,
)


def extract_themed_blocks(body_md):
    """Extract blocks marked with `<!-- code-theme: X -->` and highlight them
    with that specific theme (instead of the document-wide theme). Replace them
    with a plain-text marker and return (modified_markdown, {marker: html}) so
    the already-highlighted HTML can be re-injected after Markdown conversion."""
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
# Sizes bumped +1 pt over the previous version, except the header/footer, which
# stay at 9.5 pt.

BASE_CSS = """
html, body {
    margin: 0;
    padding: 0;
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
}

/* ── Cover ── */
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
    font-size: 26pt;
    font-weight: bold;
    border: none;
    margin: 0 0 20px 0;
    line-height: 1.3;
}
.cover .subtitle  { font-size: 15pt; font-style: italic; color: #444; margin: 0 0 6px 0; }
.cover .meta-line { font-size: 11.5pt; color: #555; margin: 3px 0; }
.cover .logo      { max-width: 180px; max-height: 180px; object-fit: contain; margin: 40px 0; }
.cover .author    { font-size: 13pt; font-style: italic; color: #333; padding-bottom: 1cm; }

/* ── Table of contents ── */
.toc-page { break-after: page; font-family: 'Source Serif 4', Georgia, serif; }
.toc-page h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 17pt; margin-bottom: 20px; }
/* TOC font: force the document serif on every element of the TOC tree, so it
   doesn't inherit a system font. */
.toc-page .toc, .toc-page .toc * { font-family: 'Source Serif 4', Georgia, serif; }
.toc-page .toc { margin: 0; padding: 0; }
.toc-page .toc ul { list-style: none; margin: 0; padding: 0; }
.toc-page .toc li { padding: 5px 0; }
.toc-page .toc li li { padding-left: 2em; font-weight: normal; }
.toc-page .toc > ul > li { font-weight: bold; }
.toc-page .toc a { text-decoration: none; color: #1a1a1a; }

/* ── Lists of figures/tables/code ── */
.indices-section { break-after: page; font-family: 'Source Serif 4', Georgia, serif; }
.idx-block { margin-bottom: 32px; }
.idx-block h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 17pt; margin-bottom: 16px; }
.doc-index { list-style: none; margin: 0; padding: 0; }
.doc-index li { padding: 5px 0; }
.doc-index a { text-decoration: none; color: #1a1a1a; }
.idx-label { font-weight: bold; }

/* ── Content ── */
a { color: #5a8fc4; }
h1, h2, h3, h4, h5, h6 { font-family: 'Space Grotesk', Arial, sans-serif; }
h1 { font-size: 19pt; margin-bottom: 16px; }
/* Each ## section starts on a new page. The forced break after the TOC and this
   one merge, so no blank page appears. */
.body h2 { break-before: page; }
h2 { font-size: 16pt; margin-top: 28px; }
h3 { font-size: 13.5pt; margin-top: 20px; color: #222; }
h4 { font-size: 12pt; margin-top: 18px; color: #333; }
h5 { font-size: 11pt; margin-top: 16px; color: #444; }
code {
    font-family: 'Space Mono', 'DejaVu Sans Mono', monospace;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 10.5pt;
}
pre {
    font-family: 'Space Mono', 'DejaVu Sans Mono', monospace;
    background: #f4f4f4;
    border-radius: 4px;
    padding: 12px;
    font-size: 10pt;
    line-height: 1.4;
    break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
}
pre code { background: none; padding: 0; }
/* Highlighted blocks (codehilite with noclasses): the <div> carries the theme's
   background color inline; we make the inner <pre> transparent and move the
   padding/radius to the <div>, so dark themes (monokai, dracula…) also work
   without the grey `pre` background covering them. */
.codehilite { background: #f4f4f4; border-radius: 4px; padding: 12px; break-inside: avoid; }
.codehilite pre { background: transparent; padding: 0; margin: 0; border-radius: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10.5pt; break-inside: avoid; }
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
figcaption { font-size: 9.5pt; color: #555; margin-top: 5px; font-style: italic; }
caption { caption-side: bottom; font-size: 9.5pt; color: #555; padding-top: 6px; font-style: italic; text-align: center; }
.code-block { margin: 12px 0; break-inside: avoid; }
.code-block > pre, .code-block > .codehilite { margin: 0; }
.code-label { font-size: 9.5pt; color: #555; margin: 4px 0 0; font-style: italic; text-align: center; }

/* ── Citations and bibliography ── */
a.cite { text-decoration: none; }
.ref-entry {
    display: block;
    margin: 6px 0;
    padding-left: 1.6em;
    text-indent: -1.6em;   /* hanging indent: the first line sticks out */
}

/* ── Keep with the previous element ──
   Prevents a page break *before* the element and lets the element itself split
   if it doesn't fit, so it stays attached to the preceding text. The
   `break-inside: auto` must also reach the inner `.codehilite`/`pre`: otherwise
   a block taller than a page keeps its "don't break inside" mark, makes "keep
   with previous" unsolvable, and WeasyPrint pushes the block down leaving a
   huge gap. */
.keep-with-prev { break-before: avoid; }
.keep-with-prev,
.keep-with-prev .codehilite,
.keep-with-prev pre { break-inside: auto; }

/* PDF outline: only the body sections, not the cover or the indexes. Which
   levels are included (and the individual marks) is added by outline_css()
   based on the TOC depth, so they match the table of contents. */
h1, h2, h3, h4, h5, h6 { bookmark-level: none; }
"""


def _css_str(s):
    """Escape a string for embedding in a CSS `content:` value."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ─────────────────────── Per-section font sizes ───────────────────────
# Each front-matter (or `.theme`) key adjusts the font size of one section of the
# document. They are emitted as CSS rules *after* BASE_CSS, so they win by
# cascade order (same or higher specificity). The header/footer keys are applied
# separately, inside the @page margin boxes.
FONT_SIZE_SELECTORS = {
    "text_size":     "html, body",             # the body text
    "title_size":    ".cover h1",              # the cover title
    "subtitle_size": ".cover .subtitle",       # the cover subtitle
    "comment_size":  ".cover .meta-line",      # the cover comment line
    "author_size":   ".cover .author",         # the cover author line
    "h1_size":       ".body h1",               # body headings, per level
    "h2_size":       ".body h2",
    "h3_size":       ".body h3",
    "h4_size":       ".body h4",
    "h5_size":       ".body h5",
    "h6_size":       ".body h6",
    "code_size":     "pre, code, .codehilite pre",  # code blocks and inline code
    "table_size":    "table",                  # tables
    # figure captions, table captions, and code-block labels (one knob)
    "caption_size":  "figcaption, caption, .code-label",
    # the "Contents" / "List of …" headings on the generated index pages
    "index_heading_size": ".toc-page h2, .idx-block h2",
}

# Default size of the page header and footer (the @page margin boxes).
DEFAULT_HEADER_FOOTER_SIZE = "9pt"


def _font_size(val):
    """Normalize a font-size value: a bare number is read as points
    (`14` -> `14pt`); any other valid CSS unit (`1.2em`, `12px`…) is kept as-is.
    Empty string if nothing was given."""
    v = (val or "").strip()
    if not v:
        return ""
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return f"{v}pt"
    return v


def font_size_css(meta):
    """CSS font-size rules for the sections the front matter (or the `.theme`)
    customizes. Embedded after BASE_CSS to override the default sizes. The header
    and footer are adjusted in page_css."""
    rules = []
    for key, selector in FONT_SIZE_SELECTORS.items():
        size = _font_size(meta.get(key))
        if size:
            rules.append(f"{selector} {{ font-size: {size}; }}")
    return "\n".join(rules)


# ─────────────────────── Table-of-contents line sizes ───────────────────────
# The TOC lines are sized per nesting level (1 = top-level `##` sections, 2 =
# `###`, 3 = `####`, 4 = `#####`). Each deeper selector is more specific than the
# one above, so a level's size overrides whatever it would inherit from its
# parent. Levels beyond 4 inherit the level-4 size. These sizes are no longer in
# BASE_CSS; toc_size_css() always emits them so it fully controls TOC sizing.
TOC_LEVEL_SELECTORS = {
    1: ".toc-page .toc > ul > li",
    2: ".toc-page .toc > ul > li > ul > li",
    3: ".toc-page .toc > ul > li > ul > li > ul > li",
    4: ".toc-page .toc > ul > li > ul > li > ul > li > ul > li",
}

# Default TOC line size per level (smaller and gently decreasing with depth).
TOC_DEFAULT_SIZES = {1: "11pt", 2: "10.5pt", 3: "10pt", 4: "10pt"}

# Default size of the figure/table/code list lines (a flat, single-level list,
# so it has no per-level keys — it just follows the general `toc_size`).
TOC_INDEX_DEFAULT_SIZE = "10.5pt"


def toc_size_css(meta):
    """CSS font-size rules for the table-of-contents lines, per nesting level.
    `toc_size` sets every level at once; `toc1_size`…`toc4_size` override an
    individual level (1 = top-level `##` sections, 2 = `###`, 3 = `####`,
    4 = `#####`). Each level falls back to the general `toc_size`, then to the
    built-in default in TOC_DEFAULT_SIZES. The general `toc_size` also sizes the
    figure/table/code lists (`.doc-index li`)."""
    general = _font_size(meta.get("toc_size"))
    rules = []
    for level, selector in TOC_LEVEL_SELECTORS.items():
        size = (_font_size(meta.get(f"toc{level}_size")) or general
                or TOC_DEFAULT_SIZES[level])
        rules.append(f"{selector} {{ font-size: {size}; }}")
    rules.append(f".doc-index li {{ font-size: {general or TOC_INDEX_DEFAULT_SIZE}; }}")
    return "\n".join(rules)


def resolve_page_size(meta):
    """Resolve `page_size` + `orientation` to a CSS value for `@page { size }`
    (e.g. 'A4' or 'letter landscape'). Warn and fall back to the default if the
    size or orientation are unknown (same as with `code_theme`)."""
    name = (meta.get("page_size") or "").strip().lower()
    size = PAGE_SIZES.get(name, "A4") if name else "A4"
    if name and name not in PAGE_SIZES:
        print(f"    (warning: unknown page size '{name}'; using A4)",
              file=sys.stderr)
    orient = (meta.get("orientation") or "").strip().lower()
    if orient in ("landscape", "apaisado", "horizontal"):
        return f"{size} landscape"
    if orient and orient not in ("portrait", "vertical", "retrato"):
        print(f"    (warning: unknown orientation '{orient}'; using portrait)",
              file=sys.stderr)
    return size


def resolve_margins(meta):
    """Resolve the body margins to a CSS value `top right bottom left`. Prefers
    `margins` (literal CSS, e.g. '1.15in 0.85in'); otherwise composes them from
    the per-side keys (`margin_top`…), using the default for any that are
    missing."""
    whole = (meta.get("margins") or "").strip()
    if whole:
        return whole
    sides = ("margin_top", "margin_right", "margin_bottom", "margin_left")
    return " ".join((meta.get(k) or "").strip() or d
                    for k, d in zip(sides, DEFAULT_MARGINS))


# Default depth of the table of contents: down to `####` (level 4). `#####`
# (level 5) doesn't appear unless this depth is raised with `toc_depth` or the
# specific heading is marked with `<!-- toc -->`.
DEFAULT_TOC_DEPTH = 4


def resolve_toc_depth(meta):
    """Resolve `toc_depth`: the deepest heading level that enters the table of
    contents (3 = down to `###`, 4 = down to `####`, 5 = down to `#####`).
    Default 4. Accepts '3'/'4'/'5', 'h4', '####'… Warn and fall back to the
    default if the value is unknown (same as with `code_theme`)."""
    raw = (meta.get("toc_depth") or "").strip().lower()
    if not raw:
        return DEFAULT_TOC_DEPTH
    if raw.count("#") >= 2:
        depth = raw.count("#")
    else:
        m = re.search(r"[2-6]", raw)
        depth = int(m.group(0)) if m else 0
    if 2 <= depth <= 6:
        return depth
    print(f"    (warning: invalid TOC depth '{raw}'; using "
          f"{DEFAULT_TOC_DEPTH})", file=sys.stderr)
    return DEFAULT_TOC_DEPTH


def page_css(meta, strings, page_size):
    """Body @page: size + margins + header (title · subtitle) and footer (author
    centered, 'n / total' on the right). The text is embedded as CSS strings;
    the margin boxes clip whatever overflows."""
    header = " · ".join(filter(None, [meta.get("title", ""), meta.get("subtitle", "")]))
    author = meta.get("author", "")
    top = (f'content: "{_css_str(header)}";' if header else "content: none;")
    bottom = (f'content: "{_css_str(author)}";' if author else "content: none;")
    header_size = _font_size(meta.get("header_size")) or DEFAULT_HEADER_FOOTER_SIZE
    footer_size = _font_size(meta.get("footer_size")) or DEFAULT_HEADER_FOOTER_SIZE
    return f"""
@page {{
    size: {page_size};
    margin: {resolve_margins(meta)};
    @top-center {{
        {top}
        font-family: 'Space Grotesk', Arial, sans-serif;
        font-size: {header_size}; color: #666;
        white-space: nowrap; overflow: hidden;
    }}
    @bottom-center {{
        {bottom}
        font-family: 'Space Grotesk', Arial, sans-serif;
        font-size: {footer_size}; color: #666;
        white-space: nowrap; overflow: hidden;
    }}
    @bottom-right {{
        content: counter(page) " / " counter(pages);
        font-family: 'Space Grotesk', Arial, sans-serif;
        font-size: {footer_size}; color: #666;
    }}
}}
"""


# ─────────────────────── Front matter / metadata ───────────────────────
# Keys accept English names and Spanish aliases (titulo, autor, imagen…) so
# either language works in the front matter and in `.theme` files.

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
    "toc_depth": "toc_depth", "tocdepth": "toc_depth",
    "toc_level": "toc_depth", "toc_levels": "toc_depth",
    "profundidad_indice": "toc_depth", "profundidad_índice": "toc_depth",
    "nivel_indice": "toc_depth", "nivel_índice": "toc_depth",
    "profundidad_toc": "toc_depth",
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
    # .theme file (path relative to the .md, like `logo` or `bibliography`).
    "theme": "theme", "tema": "theme", "estilo": "theme", "style": "theme",
    "theme_file": "theme", "fichero_tema": "theme", "archivo_tema": "theme",
    # Per-section font sizes.
    "text_size": "text_size", "font_size": "text_size", "body_size": "text_size",
    "tamano_texto": "text_size", "tamaño_texto": "text_size",
    "tamano_letra": "text_size", "tamaño_letra": "text_size",
    "title_size": "title_size", "tamano_titulo": "title_size",
    "tamaño_titulo": "title_size", "tamaño_título": "title_size",
    "tamano_portada": "title_size", "tamaño_portada": "title_size",
    "subtitle_size": "subtitle_size", "tamano_subtitulo": "subtitle_size",
    "tamaño_subtitulo": "subtitle_size", "tamaño_subtítulo": "subtitle_size",
    "comment_size": "comment_size", "tamano_comentario": "comment_size",
    "tamaño_comentario": "comment_size",
    "author_size": "author_size", "tamano_autor": "author_size",
    "tamaño_autor": "author_size",
    "h1_size": "h1_size", "tamano_h1": "h1_size", "tamaño_h1": "h1_size",
    "h2_size": "h2_size", "tamano_h2": "h2_size", "tamaño_h2": "h2_size",
    "h3_size": "h3_size", "tamano_h3": "h3_size", "tamaño_h3": "h3_size",
    "h4_size": "h4_size", "tamano_h4": "h4_size", "tamaño_h4": "h4_size",
    "h5_size": "h5_size", "tamano_h5": "h5_size", "tamaño_h5": "h5_size",
    "h6_size": "h6_size", "tamano_h6": "h6_size", "tamaño_h6": "h6_size",
    "code_size": "code_size", "tamano_codigo": "code_size",
    "tamaño_codigo": "code_size", "tamaño_código": "code_size",
    "table_size": "table_size", "tamano_tabla": "table_size",
    "tamaño_tabla": "table_size", "tamano_tablas": "table_size",
    "tamaño_tablas": "table_size",
    "caption_size": "caption_size", "tamano_pie_figura": "caption_size",
    "tamaño_pie_figura": "caption_size", "tamano_leyenda": "caption_size",
    "tamaño_leyenda": "caption_size",
    "index_heading_size": "index_heading_size",
    "tamano_titulo_indice": "index_heading_size",
    "tamaño_titulo_indice": "index_heading_size",
    "tamaño_título_índice": "index_heading_size",
    "header_size": "header_size", "tamano_cabecera": "header_size",
    "tamaño_cabecera": "header_size",
    "footer_size": "footer_size", "tamano_pie": "footer_size",
    "tamaño_pie": "footer_size", "tamano_footer": "footer_size",
    "tamaño_footer": "footer_size",
    # Table-of-contents line sizes: general + per nesting level.
    "toc_size": "toc_size", "toc_line_size": "toc_size",
    "tamano_indice": "toc_size", "tamaño_indice": "toc_size",
    "tamaño_índice": "toc_size", "tamano_toc": "toc_size",
    "tamaño_toc": "toc_size",
    "toc1_size": "toc1_size", "toc_l1_size": "toc1_size",
    "toc2_size": "toc2_size", "toc_l2_size": "toc2_size",
    "toc3_size": "toc3_size", "toc_l3_size": "toc3_size",
    "toc4_size": "toc4_size", "toc_l4_size": "toc4_size",
}


# Defaults for every metadata field. The `.theme` keys are layered on top of this
# base first, and the .md's own front matter on top of that (it wins). The size
# keys stay empty: an empty string means "use the BASE_CSS default size".
DEFAULT_META = {
    "title": "", "subtitle": "", "comment": "", "author": "",
    "logo": "", "lang": "es", "code_theme": "", "numbering": "true",
    "toc_depth": "",
    "page_size": "", "orientation": "", "margins": "",
    "margin_top": "", "margin_right": "", "margin_bottom": "",
    "margin_left": "", "bibliography": "", "citation_style": "",
    "theme": "",
    "text_size": "", "title_size": "",
    "subtitle_size": "", "comment_size": "", "author_size": "",
    "h1_size": "", "h2_size": "", "h3_size": "", "h4_size": "",
    "h5_size": "", "h6_size": "",
    "code_size": "", "table_size": "", "caption_size": "",
    "index_heading_size": "",
    "header_size": "", "footer_size": "",
    "toc_size": "", "toc1_size": "", "toc2_size": "", "toc3_size": "",
    "toc4_size": "",
}


# Free-text keys whose value may legitimately contain a `#` (e.g. a title like
# "Issue #42"), so inline-comment stripping is skipped for them.
_PROSE_KEYS = {"title", "subtitle", "comment", "author"}


def parse_kv_lines(lines):
    """Read `key: value` lines (front matter or `.theme`) into a dict holding
    only the keys that are *present* (canonicalized via _META_ALIASES). It does
    not apply defaults: this way the caller knows which keys were actually set
    and can give some sources precedence over others.

    An inline comment is supported: the first `#` that is preceded by whitespace
    starts a comment and is dropped (`key: value   # note` keeps just `value`).
    A `#` with no space before it (e.g. a `#rrggbb` color) is left intact. The
    free-text keys in _PROSE_KEYS keep everything (a title may contain `#`)."""
    meta = {}
    for raw in lines:
        if ":" not in raw:
            continue
        key, val = raw.split(":", 1)
        canon = _META_ALIASES.get(key.strip().lower())
        if not canon:
            continue
        if canon not in _PROSE_KEYS:
            val = re.split(r"\s+#", val, maxsplit=1)[0]
        meta[canon] = val.strip().strip('"').strip("'").strip()
    return meta


def parse_front_matter(text):
    """Read a simple YAML front-matter block (`key: value`) delimited by `---`
    lines at the start of the file. Returns (meta, body), where `meta` holds only
    the keys *present* in the front matter (no defaults); the caller merges them
    with the `.theme` and DEFAULT_META.

    If there is no title in the front matter, it is taken from the first `# `
    heading (which is removed from the body so it isn't duplicated). That heading
    title takes precedence over any the `.theme` might carry."""
    lines = text.splitlines()
    body_start = 0
    meta = {}

    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                meta = parse_kv_lines(lines[1:i])
                body_start = i + 1
                break

    body_lines = lines[body_start:]

    if not meta.get("title"):
        for idx, line in enumerate(body_lines):
            if line.startswith("# "):
                meta["title"] = line[2:].strip()
                del body_lines[idx]
                break

    return meta, "\n".join(body_lines)


def load_theme(md_path, md_meta):
    """Load the `.theme` named in `theme:` (path relative to the .md, like the
    logo or the bibliography) and return its explicit keys. The `.theme` has the
    same `key: value` format as the front matter; it may (optionally) be
    delimited by `---` lines, so a front matter can be reused as a theme. With no
    `theme` field, returns {}. Raises ValueError if the file does not exist."""
    field = (md_meta.get("theme") or "").strip()
    if not field or field.lower() in ("none", "no", "false"):
        return {}
    p = Path(field)
    theme_path = p if p.is_absolute() else md_path.parent / p
    if not theme_path.exists():
        raise ValueError(f"theme '{field}' not found")
    lines = theme_path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "---":
        inner = []
        for ln in lines[1:]:
            if ln.strip() == "---":
                break
            inner.append(ln)
        lines = inner
    theme_meta = parse_kv_lines(lines)
    theme_meta.pop("theme", None)   # a .theme does not chain to another .theme
    return theme_meta


def find_logo(md_path, meta):
    """Resolve the cover logo/image to a data URI from the `logo:` field of the
    front matter (arbitrary path relative to the .md, or absolute). If `logo:` is
    not given, the cover has no image. `logo: none` also disables it
    explicitly."""
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


# ─────────────────────── Section numbering and cross-references ───────────────────────

_HEADING_RE = re.compile(r'^(#{2,6})\s+(.*)$')
_FENCE_RE = re.compile(r'^\s*(```|~~~)')


def apply_section_numbering(body_md):
    """Auto-number section headings (`##` -> 1, 2, 3…) and subsection headings
    (`###` -> 1.1, 1.2…) in the Markdown before converting it, so the number
    appears the same in the body, the table of contents, and the PDF bookmarks
    (outline), without the author writing it by hand.

    Numbers `##` (1.), `###` (1.1), `####` (1.1.1) and `#####` (1.1.1.1),
    resetting the lower-level counters when moving up a section. Ignores headings
    inside code fences. Enabled by default; disable it with `numbering: false` in
    the front matter if the document already carries hand-written numbering (to
    avoid duplicating it)."""
    h2 = h3 = h4 = h5 = 0
    in_fence = False
    out = []
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        level = len(m.group(1)) if m else 0
        if level == 2:
            h2 += 1
            h3 = h4 = h5 = 0
            out.append(f"## {h2}. {m.group(2)}")
        elif level == 3:
            h3 += 1
            h4 = h5 = 0
            out.append(f"### {h2}.{h3} {m.group(2)}")
        elif level == 4:
            h4 += 1
            h5 = 0
            out.append(f"#### {h2}.{h3}.{h4} {m.group(2)}")
        elif level == 5:
            h5 += 1
            out.append(f"##### {h2}.{h3}.{h4}.{h5} {m.group(2)}")
        else:
            out.append(line)
    return "\n".join(out)


# Per-heading TOC marks: a `<!-- toc -->` comment (force the inclusion of a
# heading that exceeds the default depth, e.g. a `#####`) or `<!-- no-toc -->`
# (exclude one that would otherwise enter) on the line right above the heading.
# They are translated into an `attr_list` class on the heading itself, which
# collect_toc_overrides then locates by its id.
_TOC_MARK_RE = re.compile(r'^\s*<!--\s*(no-?toc|toc)\s*-->\s*$', re.IGNORECASE)


def _add_heading_class(line, cls):
    """Add an `attr_list` class to a heading line, merging it with an existing
    `{: ... }` block if there is one."""
    m = re.search(r'\{:?\s*([^}]*)\}\s*$', line)
    if m:
        inner = m.group(1).strip()
        return f"{line[:m.start()].rstrip()} {{: {inner} .{cls} }}"
    return f"{line.rstrip()} {{: .{cls} }}"


def apply_toc_markers(body_md):
    """Translate the `<!-- toc -->` / `<!-- no-toc -->` comments placed above a
    heading into a class (`toc-force` / `toc-skip`) on that heading, and remove
    the comment. Allows blank lines between the mark and the heading. Ignores
    marks inside code fences."""
    out = []
    pending = None        # 'toc-force' | 'toc-skip' | None
    in_fence = False
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            pending = None
            out.append(line)
            continue
        if not in_fence:
            mark = _TOC_MARK_RE.match(line)
            if mark:
                pending = "toc-skip" if mark.group(1).lower().startswith("no") \
                    else "toc-force"
                continue                      # drop the comment
            if _HEADING_RE.match(line):
                if pending:
                    line = _add_heading_class(line, pending)
                pending = None
            elif line.strip():
                pending = None                # only blank lines are allowed
        out.append(line)
    return "\n".join(out)


# Cross-reference `[[fig-2-1]]` / `[[tab-1-1]]` / `[[code-3-2]]`: points at the
# anchors add_asset_numbers generates. The pattern is strict (type-x-y) so it
# doesn't capture double brackets that appear by chance in the text or code.
_XREF_RE = re.compile(r'\[\[\s*((?:fig|tab|code)-\d+-\d+)\s*\]\]')


def resolve_cross_refs(html, figures, tables, code_blocks):
    """Resolve cross-references `[[fig-2-1]]` into a link to the element's anchor,
    showing its number as the visible text (e.g. "Figure 2.1"). Warns about
    references to non-existent anchors and leaves them untouched so the author can
    find them (same as with an unknown `code_theme`)."""
    labels = {aid: nl for nl, cap, aid in (*figures, *tables, *code_blocks)}

    def repl(m):
        aid = m.group(1)
        label = labels.get(aid)
        if not label:
            print(f"    (warning: cross-reference to non-existent '{aid}')",
                  file=sys.stderr)
            return m.group(0)
        return f'<a href="#{aid}" class="xref">{escape(label)}</a>'

    return _XREF_RE.sub(repl, html)


# ─────────────────────── Bibliography and citations ───────────────────────
# In-body citation: `[@key]` or several together `[@key1; @key2]`. Each key is
# replaced by a linked marker (numeric `[1]` or author-year `(Pérez, 2020)`) that
# jumps to its entry in the references section, generated from the entries
# actually cited. The bibliography is read from a `.bib` (BibTeX) named in the
# front matter with `bibliography:` (path relative to the .md, like `logo`).
_CITE_GROUP_RE = re.compile(r'\[@[^\]]+\]')
_CITE_KEY_RE = re.compile(r'@([\w:.\-]+)')
_INLINE_CODE_RE = re.compile(r'`+[^`]*`+')

# Supported citation styles (normalized key -> canonical style).
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
    """Resolve `citation_style`: 'numeric' (default) or 'author-year'. Warn and
    fall back to 'numeric' if the value is unknown (same as with `code_theme`)."""
    name = (meta.get("citation_style") or "").strip().lower()
    if name in _CITE_STYLES:
        return _CITE_STYLES[name]
    print(f"    (warning: unknown citation style '{name}'; using numeric)",
          file=sys.stderr)
    return "numeric"


def load_bibliography(md_path, meta):
    """Load the `.bib` named in `bibliography:` (path relative to the .md, like
    the logo) and return its entries (dict key->pybtex entry, case-insensitive).
    With no `bibliography` field, returns {} (no bibliography). Raises ValueError
    if the file does not exist or pybtex is missing."""
    field = (meta.get("bibliography") or "").strip()
    if not field:
        return {}
    p = Path(field)
    bib_path = p if p.is_absolute() else md_path.parent / p
    if not bib_path.exists():
        raise ValueError(f"bibliography '{field}' not found")
    try:
        from pybtex.database import parse_file
    except ImportError:
        raise ValueError("the bibliography needs 'pybtex' (install it with: uv sync)")
    return parse_file(str(bib_path)).entries


def _ref_anchor(key):
    """Stable anchor for a bibliography entry (`ref-<key>`)."""
    return "ref-" + re.sub(r'[^a-z0-9]+', '-', key.lower()).strip('-')


def _clean(value):
    """Plain text of a BibTeX field: strip braces and stray whitespace."""
    return str(value).replace("{", "").replace("}", "").strip()


def _persons(entry):
    return entry.persons.get("author") or entry.persons.get("editor") or []


def _person_last(p):
    return _clean(" ".join(p.prelast_names + p.last_names))


def _person_full(p):
    """Surname(s) + initials: "Pérez, J. M."."""
    last = _person_last(p)
    initials = " ".join(f"{_clean(n)[0]}." for n in (p.first_names + p.middle_names)
                        if _clean(n))
    if last and initials:
        return f"{last}, {initials}"
    return last or initials


def _entry_year(entry, strings):
    return _clean(entry.fields.get("year", "")) or strings["no_date"]


def _authors_full(entry, lang):
    """Author list for the references entry ("A, B and C")."""
    names = [_person_full(p) for p in _persons(entry)]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    conn = " y " if lang == "es" else " & "
    return ", ".join(names[:-1]) + conn + names[-1]


def _authors_short(entry, lang):
    """Abbreviated surnames for the author-year marker ("Pérez", "Pérez et al.")."""
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
    """Entry formatted consistently: "Authors (year). *Title*. Container."."""
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
    """Replace the body's `[@key]` citations with linked markers and build the
    references section from the cited entries. Returns
    (markdown_with_markers, references_markdown|None).

    Numbers the keys in order of first appearance. The markers jump to the
    entry's `ref-<key>` anchor. Warns about keys missing from the `.bib` and
    leaves `@key` visible. Ignores citations inside code fences."""
    cited = []            # cited keys, in order of first appearance
    number = {}           # key (lowercase) -> number

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
                print(f"    (warning: citation '@{key}' is not in the bibliography)",
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
        # Substitute outside inline-code spans (`...`), so a `[@key]` written as
        # an example between backticks is left untouched.
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

    # List order: by citation number (numeric) or alphabetical by author
    # (author-year). Each entry carries its `ref-<key>` anchor.
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


# ─────────────────────── Figure/table/code numbering ───────────────────────

def add_asset_numbers(html, strings):
    """Number figures, tables and code blocks (x.y, resetting on each `<h2>`),
    add their label, and collect the data for the indexes.

    Returns (html, figures, tables, code_blocks, missing). `missing` lists the
    labels of the elements WITHOUT a caption: an image uses its `alt`; tables and
    code blocks require `<!-- caption: -->`. If `missing` is not empty, the
    caller refuses to generate the PDF."""
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
            return ""   # remove the comment from the output
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
    """Apply the `<!-- keep -->` mark: add the keep-with-prev class to the next
    block element, forcing it to stay on the same page as the preceding content.
    Runs after numbering, so the mark affects the already-created
    <figure>/<div class="code-block"> wrapper."""
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


# ─────────────────────── Table of contents ───────────────────────

_TOC_HEADING_RE = re.compile(r'<h[2-6]\b([^>]*)>', re.IGNORECASE)


def collect_toc_overrides(html):
    """Collect the ids of headings marked individually for the TOC: `toc-force`
    (force their inclusion even if they exceed the default depth) and `toc-skip`
    (exclude them even if they would enter). The classes are injected by
    apply_toc_markers from the `<!-- toc -->` / `<!-- no-toc -->` comments."""
    force, skip = set(), set()
    for m in _TOC_HEADING_RE.finditer(html):
        attrs = m.group(1)
        id_m = re.search(r'\bid="([^"]+)"', attrs)
        cls_m = re.search(r'\bclass="([^"]*)"', attrs)
        if not id_m or not cls_m:
            continue
        classes = cls_m.group(1).split()
        if "toc-force" in classes:
            force.add(id_m.group(1))
        if "toc-skip" in classes:
            skip.add(id_m.group(1))
    return force, skip


def _toc_items(tokens, max_level, force_ids, skip_ids):
    """List of TOC `<li>` items from the heading tree. A heading enters if it is
    not marked `toc-skip` and either its level does not exceed `max_level` or it
    is marked `toc-force`. Forced descendants of an excluded heading move up a
    level so they aren't lost."""
    items = []
    for tok in tokens:
        children = _toc_items(tok.get("children", []), max_level, force_ids, skip_ids)
        tid = tok.get("id", "")
        shown = tid not in skip_ids and (tok["level"] <= max_level or tid in force_ids)
        if shown:
            sub = f'\n<ul>\n{"".join(children)}</ul>\n' if children else ""
            link = f'<a href="#{tid}">{escape(tok.get("name", ""))}</a>'
            items.append(f"<li>{link}{sub}</li>\n")
        else:
            items.extend(children)
    return items


def build_toc_html(toc_tokens, max_level, force_ids, skip_ids):
    """Build the table-of-contents HTML from `md.toc_tokens`, including by default
    down to `max_level` (`toc_depth`) and respecting the individual
    `<!-- toc -->` / `<!-- no-toc -->` marks."""
    items = _toc_items(toc_tokens, max_level, force_ids, skip_ids)
    return f'<div class="toc">\n<ul>\n{"".join(items)}</ul>\n</div>'


def outline_css(depth):
    """`bookmark-level` rules for the PDF outline, generated from the TOC depth so
    they match it: levels `##`…`#depth#` are marked; deeper ones only if forced
    with `<!-- toc -->` (`toc-force`), and those marked `<!-- no-toc -->`
    (`toc-skip`) are omitted."""
    lines = []
    for level in range(2, 7):
        bl = level - 1
        if level <= depth:
            lines.append(f".body h{level} {{ bookmark-level: {bl}; }}")
        else:
            lines.append(f".body h{level} {{ bookmark-level: none; }}")
            lines.append(f".body h{level}.toc-force {{ bookmark-level: {bl}; }}")
    lines.append(".body .toc-skip { bookmark-level: none; }")
    return "\n".join(lines)


def _indices_html(figures, tables, code_blocks, strings):
    """Build the indexes section (figures/tables/code) for the non-empty ones."""
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


# ─────────────────────────── HTML (cover and content) ───────────────────────────

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
<style>@page {{ size: {page_size}; margin: 0; }}{font_face_css()}{BASE_CSS}{font_size_css(meta)}</style>
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
    """TOC + indexes + body in a single HTML. Raises ValueError if any element
    lacks a caption."""
    # The TocExtension captures every level (2-6); the real TOC depth (toc_depth)
    # and the individual marks are applied later when building the TOC from
    # `md.toc_tokens`. `attr_list` lets us inject the `toc-force` / `toc-skip`
    # classes from the `<!-- toc -->` comments.
    md = markdown.Markdown(
        # tab_length=2 lets nested lists use the common 2-space indentation
        # (Python-Markdown defaults to 4); sane_lists keeps an ordered list
        # that follows an unordered one as a separate <ol> instead of merging
        # them into one <ul> (which rendered the numbers as bullets).
        tab_length=2,
        extensions=[TocExtension(toc_depth="2-6"), "tables", "fenced_code",
                    "codehilite", "attr_list", "sane_lists"],
        extension_configs={"codehilite": {
            "noclasses": True, "guess_lang": False, "pygments_style": code_style,
            "prestyles": f"color:{_style_fg(code_style)}"}},
    )
    # Citations and bibliography: processed before numbering so the "References"
    # section (one more `##`) enters the numbering, the TOC, and the outline.
    if bib_entries:
        body_md, refs_md = process_citations(
            body_md, bib_entries, citation_style, meta.get("lang", "es"), strings)
        if refs_md:
            body_md = f"{body_md}\n\n{refs_md}"
    # Individual TOC marks (`<!-- toc -->` / `<!-- no-toc -->`): translated into
    # classes before numbering and converting (they work whether numbering is on
    # or off).
    body_md = apply_toc_markers(body_md)
    # Automatic section numbering (on by default): applied to the Markdown before
    # converting, so the number is reflected in the body, the TOC, and the
    # outline. Disabled with `numbering: false`.
    if _truthy(meta.get("numbering")):
        body_md = apply_section_numbering(body_md)
    # Blocks with their own theme are highlighted separately and re-injected after
    # conversion; the rest use the document-wide theme (code_style) via codehilite.
    body_md, themed_blocks = extract_themed_blocks(body_md)
    body = md.convert(body_md)
    toc_tokens = md.toc_tokens
    for token, snippet in themed_blocks.items():
        body = body.replace(f"<p>{token}</p>", snippet).replace(token, snippet)

    # Table of contents: default depth (toc_depth) + individual marks collected
    # from the classes apply_toc_markers left on the headings of the converted
    # body.
    toc_depth = resolve_toc_depth(meta)
    force_ids, skip_ids = collect_toc_overrides(body)
    toc_tree = build_toc_html(toc_tokens, toc_depth, force_ids, skip_ids)

    body, figures, tables, code_blocks, missing = add_asset_numbers(body, strings)
    if missing:
        raise ValueError(
            "elements without a caption (add <!-- caption: ... --> or an alt): "
            + ", ".join(missing)
        )
    body = resolve_cross_refs(body, figures, tables, code_blocks)
    body = apply_keep_with_prev(body)
    indices = _indices_html(figures, tables, code_blocks, strings)
    lang = meta.get("lang", "es")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8">
<style>{page_css(meta, strings, page_size)}{font_face_css()}{BASE_CSS}{font_size_css(meta)}{toc_size_css(meta)}{outline_css(toc_depth)}</style>
</head>
<body>
<div class="toc-page">
  <h2>{strings["toc"]}</h2>
  {toc_tree}
</div>
{indices}<main class="body">{body}</main>
</body>
</html>"""


# ─────────────────────────── Assembly ───────────────────────────

def merge_pdfs(cover_bytes, content_bytes, meta):
    """Prepend the cover to the content, preserving the outline and internal links
    (pypdf re-adjusts the pages), and write the document metadata."""
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


def convert_one(md_path, out_path=None):
    """Convert a single .md to .pdf. By default the PDF is written next to the .md
    with the same name; with `out_path` it is written to the given path (the `-o`
    option). Raises an exception if anything fails."""
    pdf_path = out_path or md_path.with_suffix(".pdf")
    md_text = md_path.read_text(encoding="utf-8")
    md_meta, body_md = parse_front_matter(md_text)
    # Precedence: DEFAULT_META < .theme < the .md's front matter. So an option
    # repeated in the .md wins over the one in the .theme.
    theme_meta = load_theme(md_path, md_meta)
    meta = {**DEFAULT_META, **theme_meta, **md_meta}
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


def convert_and_report(md_path, out_path=None):
    """Convert a .md, reporting in the standard format
    (`name.md → name.pdf [OK, NN KB]` / `[ERROR: …]`). With `out_path` the PDF is
    written to the given path (the `-o` option). Returns True on success. Used by
    both single conversion and --watch mode."""
    pdf_path = out_path or md_path.with_suffix(".pdf")
    print(f"  {md_path.name} → {pdf_path.name}", end=" ", flush=True)
    try:
        kb = convert_one(md_path, out_path) // 1024
        print(f"[OK, {kb} KB]")
        return True
    except Exception as e:
        print(f"[ERROR: {e}]")
        return False


def watch_files(md_files, watch_dirs):
    """Watch the .md files and rebuild their PDF every time they are saved. The
    directories given on the command line are watched whole, including .md files
    created later. Applies a small debounce so it doesn't rebuild twice on several
    consecutive save events, and exits cleanly on Ctrl-C."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("--watch mode needs 'watchdog' (install it with: uv sync)")
        sys.exit(1)

    import threading

    # Watched absolute paths -> Path to convert. The set grows with the new .md
    # files that appear in any of the given directories.
    targets = {p.resolve(): p for p in md_files}
    watched_dirs = {d.resolve() for d in watch_dirs}
    dirs = sorted(watched_dirs | {p.resolve().parent for p in md_files})

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
        if p.parent in watched_dirs:
            targets[p] = p   # new .md inside a watched directory
            return p
        return None

    class Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory and target_for(event.src_path):
                schedule(Path(event.src_path).resolve())

        on_created = on_modified

        def on_moved(self, event):
            # Some editors save by moving a temp file over the original.
            dest = getattr(event, "dest_path", "")
            if dest and target_for(dest):
                schedule(Path(dest).resolve())

    observer = Observer()
    for d in dirs:
        observer.schedule(Handler(), str(d), recursive=False)
    observer.start()

    # Initial conversion to bring the PDFs up to date on startup.
    for md_path in md_files:
        convert_and_report(md_path)
    summary = f"{len(targets)} file(s)"
    if watched_dirs:
        summary += f" and {len(watched_dirs)} directory(ies)"
    print(f"Watching {summary}. Press Ctrl-C to exit.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting --watch mode.")
    finally:
        with lock:
            for t in timers.values():
                t.cancel()
        observer.stop()
        observer.join()


def collect_md_files(args):
    """Expand the arguments into the list of .md files to convert. Each argument
    can be a specific .md file or a directory (all its .md files are taken, no
    recursion). Returns the .md files and the list of given directories (the ones
    --watch mode watches whole to detect new .md files)."""
    md_files = []
    watch_dirs = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            md_files += sorted(p.glob("*.md"))
            watch_dirs.append(p)
        else:
            md_files.append(p)
    return md_files, watch_dirs


def main():
    watch = False
    output = None
    args = []
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("--watch", "-w"):
            watch = True
        elif arg in ("--output", "-o"):
            # Output PDF name/path; the value is the next argument.
            if i + 1 >= len(rest):
                print("The -o/--output option needs a file name.")
                sys.exit(1)
            output = rest[i + 1]
            i += 1
        elif arg.startswith("--output="):
            output = arg[len("--output="):]
        elif arg.startswith("-o="):
            output = arg[len("-o="):]
        else:
            args.append(arg)
        i += 1

    if not args:
        print("Usage: md-to-pdf [--watch] [-o output.pdf] <file.md | directory> ...")
        sys.exit(1)

    md_files, watch_dirs = collect_md_files(args)

    # `-o` only makes sense when converting a single .md: with several files (or a
    # directory) you can't give them all the same name. It is warned and ignored.
    out_path = None
    if output is not None:
        if watch_dirs or len(md_files) != 1:
            print("Warning: -o/--output only applies when converting a single .md; "
                  "it is ignored and each PDF is written next to its .md.")
        else:
            out_path = Path(output)

    if watch:
        watch_files(md_files, watch_dirs)
        return

    if not md_files:
        print("No .md files")
        sys.exit(1)

    failures = sum(not convert_and_report(p, out_path) for p in md_files)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
