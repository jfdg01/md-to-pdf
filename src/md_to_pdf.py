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
import logging
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
from pygments.filter import simplefilter
from pygments.token import (Comment, Error, Generic, Keyword, Literal, Name,
                            Number, Operator, Punctuation, String, Text, Token)
from pygments.util import ClassNotFound
import pypdf
import weasyprint

# pypdf avisa «Annotation sizes differ: N vs. 0» al fusionar la portada con el
# cuerpo: clona cada página excluyendo /Annots y compara los enlaces antes de
# volver a insertarlos, así que el aviso es espurio (los enlaces internos y el
# índice del PDF salen intactos). Solo errores reales.
logging.getLogger("pypdf").setLevel(logging.ERROR)

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
        "equation":    "Ecuación",
        "idx_abbr":    "Lista de siglas",
        "references":  "Referencias",
        "and":         " y ",
        "and_list":    " y ",
        "in":          "en",
        "no":          "n.º",
        "phd":         "Tesis doctoral",
        "ms":          "Trabajo fin de máster",
        "techrep":     "Inf. téc.",
        "months":      "ene. feb. mar. abr. may. jun. jul. ago. sep. oct. nov. dic.",
        "accessed":    "Accedido:",
        "online":      "[En línea].",
        "available":   "Disponible:",
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
        "equation":    "Equation",
        "idx_abbr":    "List of acronyms",
        "references":  "References",
        "and":         " and ",
        "and_list":    ", and ",
        "in":          "in",
        "no":          "no.",
        "phd":         "Ph.D. dissertation",
        "ms":          "M.S. thesis",
        "techrep":     "Tech. Rep.",
        "months":      "Jan. Feb. Mar. Apr. May Jun. Jul. Aug. Sep. Oct. Nov. Dec.",
        "accessed":    "Accessed:",
        "online":      "[Online].",
        "available":   "Available:",
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
            # YAML: keys (`Name.Tag`, also HTML/XML tags), plain values (the
            # `Literal` parent, so String/Number keep their own entries),
            # `-`/`{` markers, anchors and aliases.
            Name.Tag:       palette["function"],
            Literal:        palette["string"],
            Punctuation.Indicator: palette["operator"],
            Name.Label:     palette["builtin"],
            Name.Variable:  palette["builtin"],
            Error:          palette["error"],
        },
    })


CUSTOM_CODE_STYLE = _build_custom_style(CODE_PALETTE)

_YAML_NUMBER = re.compile(r'[-+]?(\d[\d_]*(\.\d*)?([eE][-+]?\d+)?|\.inf|\.nan|0x[0-9a-fA-F]+)')
_YAML_CONSTANT = {"true", "false", "yes", "no", "on", "off", "null", "~"}


@simplefilter
def _yaml_scalars(self, lexer, stream, options):
    """The Pygments YAML lexer emits every unquoted value as one token type
    (`Literal.Scalar.Plain`). Give numbers the `Number` type and booleans/null
    the `Keyword.Constant` type, so every theme colors them as in an editor.
    Only YAML emits `Literal.Scalar.Plain`, so the other lexers are not
    affected. Passed to every lexer through the `filters` option."""
    for ttype, value in stream:
        if ttype is Literal.Scalar.Plain:
            if _YAML_NUMBER.fullmatch(value):
                ttype = Number
            elif value.lower() in _YAML_CONSTANT:
                ttype = Keyword.Constant
        yield ttype, value


def yml_fences(body_md):
    """Pygments has no `yml` alias (only `yaml`): rename the fence language so
    a ```yml block is highlighted too."""
    return re.sub(r'^([ \t]*(?:```|~~~)[ \t]*)yml[ \t]*$', r'\1yaml', body_md,
                  flags=re.MULTILINE)


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
            lexer = get_lexer_by_name(lang, filters=[_yaml_scalars()],
                                      startinline=True)
        except ClassNotFound:
            lexer = TextLexer()
        formatter = HtmlFormatter(style=style, noclasses=True, cssclass="codehilite",
                                  prestyles=f"color:{_style_fg(style)}")
        token = f"CODEBLOCKTHEME{len(blocks)}MARKER"
        blocks[token] = highlight(m.group("code"), lexer, formatter)
        return f"\n\n{token}\n\n"

    return _THEMED_BLOCK_RE.sub(repl, body_md), blocks


# ─────────────────────── Formulas ───────────────────────
# `$...$` inline and `$$...$$` as a block, in LaTeX. ziamath (pure Python)
# draws each one as an SVG; the formulas are swapped for markers before the
# Markdown conversion, so a `_` or a `\` in the LaTeX stays intact.
_INLINE_CODE_RE = re.compile(r'`+[^`]*`+')
# Pandoc's rule: no space just inside the `$`, and no digit or word right after
# the closing `$`, so a price like "$5 and $6" stays text.
_INLINE_MATH_RE = re.compile(r'(?<![\\$\w])\$(?=\S)([^$\n]*?\S)\$(?![\w$])')
_MATH_PX = 20   # ziamath draws at this size; math_svg turns it into em units


def sub_prose(line, fn):
    """Apply `fn` to the parts of a Markdown line outside inline code spans."""
    parts, last = [], 0
    for m in _INLINE_CODE_RE.finditer(line):
        parts += [fn(line[last:m.start()]), m.group(0)]
        last = m.end()
    return "".join(parts) + fn(line[last:])


def math_svg(latex, block):
    """The SVG of one LaTeX formula, sized in em so it follows the text size and
    sits on the text baseline. Raises ValueError on a formula ziamath rejects."""
    import ziamath
    ziamath.config.svg2 = False   # xlink:href, which WeasyPrint reads
    try:
        svg = ziamath.Latex(latex.strip(), size=_MATH_PX, inline=not block).svg()
    except Exception as e:
        raise ValueError(f"formula '{latex.strip()}': {e}")
    m = re.match(r'<svg ([^>]*)width="([\d.]+)" height="([\d.]+)" '
                 r'viewBox="[-\d.]+ ([-\d.]+)', svg)
    w, h, top = (float(m.group(i)) for i in (2, 3, 4))
    style = (f'width:{w / _MATH_PX:.3f}em;height:{h / _MATH_PX:.3f}em;'
             f'vertical-align:{-(h + top) / _MATH_PX:.3f}em')
    return svg.replace(m.group(0), f'<svg {m.group(1)}style="{style}" '
                       f'viewBox="{m.group(0).split("viewBox=")[1][1:]}', 1)


def extract_math(body_md):
    """Swap each formula outside code for a marker. Returns (markdown,
    {marker: html}, {marker: LaTeX}); the TOC shows the LaTeX. A block starts with a line that begins with `$$` and ends
    with a line that ends with `$$`; it becomes a `<div class="math-block">`,
    which add_asset_numbers numbers."""
    tokens, sources = {}, {}

    def put(html, latex):
        token = f"MATHFORMULA{len(tokens)}MARKER"
        tokens[token], sources[token] = html, latex.strip()
        return token

    def inline(text):
        return _INLINE_MATH_RE.sub(lambda m: put(
            f'<span class="math">{math_svg(m.group(1), False)}</span>', m.group(1)), text)

    def block_html(latex):
        return (f'<div class="math-block"><span class="math">'
                f'{math_svg(latex, True)}</span></div>')

    out, in_fence, block = [], False, None
    for line in body_md.split("\n"):
        st = line.strip()
        if block is not None:
            if st.endswith("$$"):
                block.append(st[:-2])
                latex = "\n".join(block)
                out += ["", put(block_html(latex), latex), ""]
                block = None
            else:
                block.append(line)
        elif _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
        elif in_fence:
            out.append(line)
        elif st.startswith("$$"):
            rest = st[2:]
            if len(rest) >= 2 and rest.endswith("$$"):
                out += ["", put(block_html(rest[:-2]), rest[:-2]), ""]
            else:
                block = [rest]
        else:
            out.append(sub_prose(line, inline))
    if block is not None:
        raise ValueError("a $$ formula block has no closing $$")
    return "\n".join(out), tokens, sources


# ─────────────────────────── CSS ───────────────────────────
# The body text is 11pt (`text_size`). Every other size is in rem (a multiple of
# the body size), so `text_size` scales the whole document. The value in rem is
# the old pt size / 11. The header and footer stay in pt (see page_css).

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
    font-size: 2.3636rem;
    font-weight: bold;
    border: none;
    margin: 0 0 20px 0;
    line-height: 1.3;
}
.cover .subtitle  { font-size: 1.3636rem; font-style: italic; color: #444; margin: 0 0 6px 0; }
.cover .meta-line { font-size: 1.0455rem; color: #555; margin: 3px 0; }
.cover .logo      { max-width: 180px; max-height: 180px; object-fit: contain; margin: 40px 0; }
.cover .author    { font-size: 1.1818rem; font-style: italic; color: #333; padding-bottom: 1cm; }

/* ── Title block on page 1 of a document without a cover ── */
.doc-head { text-align: center; margin-bottom: 28px; }
.doc-head .doc-title {
    font-family: 'Space Grotesk', Arial, sans-serif;
    font-size: 1.7273rem; font-weight: bold; line-height: 1.3; margin: 0 0 6px 0;
}
.doc-head .subtitle { font-style: italic; color: #444; margin: 0 0 4px 0; }
.doc-head .meta-line, .doc-head .author { color: #555; margin: 2px 0; }

/* ── Table of contents ── */
.toc-page { break-after: page; font-family: 'Source Serif 4', Georgia, serif; }
.toc-page h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 1.5455rem; margin-bottom: 20px; }
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
.idx-block h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 1.5455rem; margin-bottom: 16px; }
.doc-index { list-style: none; margin: 0; padding: 0; }
.doc-index li { padding: 5px 0; }
.doc-index a { text-decoration: none; color: #1a1a1a; }
.idx-label { font-weight: bold; }
.abbr-list { margin: 0; }
.abbr-list dt { float: left; clear: left; width: 7em; font-weight: bold; padding: 3px 0; }
.abbr-list dd { margin: 0 0 0 7.5em; padding: 3px 0; }
a.abbr { color: inherit; text-decoration: none; }

/* ── Content ── */
a { color: #5a8fc4; }
h1, h2, h3, h4, h5, h6 { font-family: 'Space Grotesk', Arial, sans-serif; }
h1 { font-size: 1.7273rem; margin-bottom: 16px; }
/* With `page_break: true`, each top-level section starts on a new page. Which
   level that is depends on the document (see detect_base_level), so the rule
   is emitted by heading_css(); the forced break after the TOC and this one
   merge, so no blank page appears. */
h2 { font-size: 1.4545rem; margin-top: 28px; }
h3 { font-size: 1.2273rem; margin-top: 20px; color: #222; }
h4 { font-size: 1.0909rem; margin-top: 18px; color: #333; }
h5 { font-size: 1rem; margin-top: 16px; color: #444; }
code {
    font-family: 'Space Mono', 'DejaVu Sans Mono', monospace;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 0.9545rem;
}
pre {
    font-family: 'Space Mono', 'DejaVu Sans Mono', monospace;
    background: #f4f4f4;
    border-radius: 4px;
    padding: 12px;
    font-size: 0.9091rem;
    line-height: 1.4;
    break-inside: avoid;
    white-space: pre-wrap;
    word-wrap: break-word;
}
pre code { background: none; padding: 0; }
table code { font-size: 1em; }  /* follows the table, which fit_wide_tables may shrink */
/* Highlighted blocks (codehilite with noclasses): the <div> carries the theme's
   background color inline; we make the inner <pre> transparent and move the
   padding/radius to the <div>, so dark themes (monokai, dracula…) also work
   without the grey `pre` background covering them. */
.codehilite { background: #f4f4f4; border-radius: 4px; padding: 12px; break-inside: avoid; }
.codehilite pre { background: transparent; padding: 0; margin: 0; border-radius: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.9545rem; break-inside: avoid; }
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
figure img {
    max-width: 100%; height: auto; display: block; margin: 0 auto;
    /* A thin dashed frame, with a small transparent gap around the image. */
    padding: 4px; border: 0.75pt dashed #808080; box-sizing: border-box;
}
/* A row of 2-4 images: one figure, each image with its "(a) alt" sub-caption. */
.img-row .row { display: table; width: 100%; table-layout: fixed; }
.img-row .sub { display: table-cell; vertical-align: bottom; padding: 0 5px; }
.subcap { display: block; font-size: 0.8636rem; color: #555; margin-top: 3px; }
figcaption { font-size: 0.8636rem; color: #555; margin-top: 5px; font-style: italic; }
caption { caption-side: bottom; font-size: 0.8636rem; color: #555; padding-top: 6px; font-style: italic; text-align: center; }
.code-block { margin: 12px 0; break-inside: avoid; }
.code-block > pre, .code-block > .codehilite { margin: 0; }
.code-label { font-size: 0.8636rem; color: #555; margin: 4px 0 0; font-style: italic; text-align: center; }
/* File-name bar from `<!-- file: path -->`: a window bar on top of the block,
   three dots on the left and the name in the center. Its colors come from the
   block's theme, set inline by code_file_bar(). */
.code-file {
    font-family: 'Space Grotesk', Arial, sans-serif;
    font-size: 0.8rem;
    padding: 5px 12px;
    border-radius: 6px 6px 0 0;
    text-align: center;
    position: relative;
    break-after: avoid;
    margin-bottom: -1px;  /* overlap the block: no light seam line between the two */
}
.code-file .dots { position: absolute; left: 12px; top: 50%; margin-top: -4px; font-size: 0; line-height: 0; }
.code-file .dots i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
.code-file .dir { opacity: 0.55; }
.code-file + .codehilite, .code-file + pre { border-radius: 0 0 6px 6px; }

/* ── Formulas: an SVG per formula; a block one is centred, number on the right ── */
.math svg { display: inline-block; }
.math-block { position: relative; text-align: center; margin: 10px 0; break-inside: avoid; }
.eq-num { position: absolute; right: 0; top: 50%; transform: translateY(-50%); }

/* ── References (IEEE): the [n] in a left column, the text in a block ── */
a.cite, a.xref { text-decoration: none; }
.ref-entry { margin: 6px 0; padding-left: 2.6em; text-indent: -2.6em; }
.ref-num { display: inline-block; width: 2.6em; text-indent: 0; }
.ref-url { overflow-wrap: anywhere; }

/* ── Footnotes: at the foot of the page of their call ── */
.fn {
    float: footnote; font-size: 0.8182rem; line-height: 1.4;
    font-style: normal; font-weight: normal; color: #1a1a1a; text-align: left;
}
.fn-again { vertical-align: super; font-size: 0.7em; line-height: 1; }
::footnote-call { content: counter(footnote); vertical-align: super; font-size: 0.7em; line-height: 1; }
::footnote-marker { content: counter(footnote) ". "; }

/* ── Keep with the previous element ──
   Prevents a page break *before* the element and lets the element itself split
   if it doesn't fit, so it stays attached to the preceding text. The
   `break-inside: auto` must also reach the inner `.codehilite`/`pre`: otherwise
   a block taller than a page keeps its "don't break inside" mark, makes "keep
   with previous" unsolvable, and WeasyPrint pushes the block down leaving a
   huge gap. */
.keep-with-prev { break-before: avoid; }
/* The element may split, but its caption never goes alone to the next page. */
.code-label, figcaption, caption { break-before: avoid; }
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
    # the cover, or the title block on page 1 of a document without a cover
    "title_size":    ".cover h1, .doc-head .doc-title",
    "subtitle_size": ".cover .subtitle, .doc-head .subtitle",
    "comment_size":  ".cover .meta-line, .doc-head .meta-line",
    "author_size":   ".cover .author, .doc-head .author",
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
    "code_file_size": ".code-file",            # the `<!-- file: -->` bar
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
TOC_DEFAULT_SIZES = {1: "1rem", 2: "0.9545rem", 3: "0.9091rem", 4: "0.9091rem"}

# Default size of the figure/table/code list lines (a flat, single-level list,
# so it has no per-level keys — it just follows the general `toc_size`).
TOC_INDEX_DEFAULT_SIZE = "0.9545rem"


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
    contents, as an absolute heading level (2 = down to `##`, 3 = down to `###`,
    4 = down to `####`). Default 4. Accepts '3'/'4'/'5', 'h4', '####'… Warn and
    fall back to the default if the value is unknown (same as with
    `code_theme`)."""
    raw = (meta.get("toc_depth") or "").strip().lower()
    if not raw:
        return DEFAULT_TOC_DEPTH
    if raw.count("#") >= 1:
        depth = raw.count("#")
    else:
        m = re.search(r"[1-6]", raw)
        depth = int(m.group(0)) if m else 0
    if 1 <= depth <= 6:
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
    @footnote {{
        border-top: 0.5pt solid #999; padding-top: 4pt; margin-top: 8pt;
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
    "page_break": "page_break", "pagebreak": "page_break",
    "salto_pagina": "page_break", "salto_página": "page_break",
    "salto_de_pagina": "page_break", "salto_de_página": "page_break",
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
    "caption_position": "caption_position", "captions": "caption_position",
    "posicion_leyenda": "caption_position", "posición_leyenda": "caption_position",
    "leyendas": "caption_position",
    "bibliography": "bibliography", "bibliografia": "bibliography",
    "bibliografía": "bibliography", "bib": "bibliography",
    # The cover, the TOC and each index can be switched off.
    "cover": "cover", "portada": "cover",
    "toc": "toc", "indice": "toc", "índice": "toc",
    "figure_index": "figure_index", "indice_figuras": "figure_index",
    "índice_figuras": "figure_index",
    "table_index": "table_index", "indice_tablas": "table_index",
    "índice_tablas": "table_index",
    "code_index": "code_index", "indice_codigo": "code_index",
    "índice_código": "code_index",
    "acronym_index": "acronym_index", "lista_siglas": "acronym_index",
    "siglas": "acronym_index",
    # .theme file (path relative to the .md, like `logo`).
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
    "code_file_size": "code_file_size", "file_size": "code_file_size",
    "tamano_archivo": "code_file_size", "tamaño_archivo": "code_file_size",
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
    "page_break": "false", "toc_depth": "",
    "page_size": "", "orientation": "", "margins": "",
    "margin_top": "", "margin_right": "", "margin_bottom": "",
    "margin_left": "", "caption_position": "", "bibliography": "",
    "theme": "",
    "text_size": "", "title_size": "",
    "subtitle_size": "", "comment_size": "", "author_size": "",
    "h1_size": "", "h2_size": "", "h3_size": "", "h4_size": "",
    "h5_size": "", "h6_size": "",
    "code_size": "", "table_size": "", "caption_size": "", "code_file_size": "",
    "index_heading_size": "",
    "header_size": "", "footer_size": "",
    "toc_size": "", "toc1_size": "", "toc2_size": "", "toc3_size": "",
    "toc4_size": "",
    "cover": "true", "toc": "true", "figure_index": "true", "table_index": "true",
    "code_index": "true", "acronym_index": "true",
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
    logo) and return its explicit keys. The `.theme` has the
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

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
_FENCE_RE = re.compile(r'^\s*(```|~~~)')

# How many levels below the top one get a number (top + 3 = `1`, `1.1`, `1.1.1`,
# `1.1.1.1`). Deeper headings are left unnumbered.
NUMBERED_LEVELS = 4


def detect_base_level(body_md):
    """The document's own top heading level: the shallowest one it actually uses
    (outside code fences).

    Two conventions are in the wild and both are valid. When the title comes from
    the front matter, `#` is free and the sections are `#`, `##`, `###`. When the
    title is the body's first `# `, that heading is consumed as the title and the
    sections start at `##`. Everything that counts levels — section numbers, the
    TOC, the PDF outline, the page break per section, figure/table numbering — is
    measured from this base, so both conventions render as `1`, `1.1`, `1.1.1`
    instead of one of them starting at `0.1`.

    Returns 2 for a body with no headings (the historical default)."""
    in_fence = False
    levels = []
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        if m:
            levels.append(len(m.group(1)))
    return min(levels) if levels else 2


def apply_section_numbering(body_md, base=2):
    """Auto-number the headings in the Markdown before converting it, so the
    number appears the same in the body, the table of contents, and the PDF
    bookmarks (outline), without the author writing it by hand.

    `base` is the document's top level (see detect_base_level): it gets `1.`,
    `2.`, `3.`…, the level below it `1.1`, then `1.1.1` and `1.1.1.1`, resetting
    the lower-level counters when moving back up. Headings deeper than
    NUMBERED_LEVELS below the base are left alone, as are those inside code
    fences. Enabled by default; disable it with `numbering: false` in the front
    matter if the document already carries hand-written numbering (to avoid
    duplicating it)."""
    counters = [0] * NUMBERED_LEVELS
    in_fence = False
    out = []
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        m = None if in_fence else _HEADING_RE.match(line)
        depth = len(m.group(1)) - base if m else -1
        if 0 <= depth < NUMBERED_LEVELS:
            counters[depth] += 1
            for i in range(depth + 1, NUMBERED_LEVELS):
                counters[i] = 0
            # The top level keeps its trailing dot ("1."); deeper ones don't
            # ("1.1"), which is the usual convention and what this tool has
            # always emitted.
            number = ".".join(str(c) for c in counters[:depth + 1])
            dot = "." if depth == 0 else ""
            out.append(f"{m.group(1)} {number}{dot} {m.group(2)}")
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


# Cross-reference `[[fig-2-1]]` / `[[tab-1-1]]` / `[[code-3-2]]` / `[[eq-2-1]]`: points at the
# anchors add_asset_numbers generates. The pattern is strict (type-x-y) so it
# doesn't capture double brackets that appear by chance in the text or code.
_XREF_RE = re.compile(r'\[\[\s*((?:fig|tab|code|eq)-\d+-\d+)\s*\]\]')


def resolve_cross_refs(html, figures, tables, code_blocks, equations=()):
    """Resolve cross-references `[[fig-2-1]]` into a link to the element's anchor,
    showing its number as the visible text (e.g. "Figure 2.1"). Warns about
    references to non-existent anchors and leaves them untouched so the author can
    find them (same as with an unknown `code_theme`)."""
    labels = {aid: nl for nl, cap, aid in (*figures, *tables, *code_blocks,
                                           *equations)}

    def repl(m):
        aid = m.group(1)
        label = labels.get(aid)
        if not label:
            print(f"    (warning: cross-reference to non-existent '{aid}')",
                  file=sys.stderr)
            return m.group(0)
        return f'<a href="#{aid}" class="xref">{escape(label)}</a>'

    return _XREF_RE.sub(repl, html)


# ─────────────────────── Bibliography (IEEE) ───────────────────────
# `bibliography: refs.bib` in the front matter (path relative to the .md) and
# `[@key]` or `[@a; @b]` in the text. Each cited key gets a number `[n]` in order
# of first appearance; a "References" section at the end lists the cited
# entries in IEEE style, each one the target of its `[n]` links.
_CITE_GROUP_RE = re.compile(r'\[@[^\]]+\]')
_CITE_KEY_RE = re.compile(r'@([\w:.\-]+)')
_BIB_URL_RE = re.compile(r'\\url\s*\{([^}]*)\}')


def load_bibliography(md_path, meta):
    """The entries of the `.bib` named in `bibliography:` (a case-insensitive
    dict key -> pybtex entry), or {} with no `bibliography`. Raises ValueError
    if the file does not exist."""
    field = (meta.get("bibliography") or "").strip()
    if not field:
        return {}
    bib_path = md_path.parent / field
    if not bib_path.exists():
        raise ValueError(f"bibliography '{field}' not found")
    from pybtex.database import parse_file
    return parse_file(str(bib_path)).entries


def _slug(prefix, text):
    return prefix + "-" + re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def _clean(value):
    """Plain text of a BibTeX field: no braces, no stray whitespace."""
    return " ".join(str(value).replace("{", "").replace("}", "").split())


def _ieee_name(p):
    """Initials first: "J. F. Dibo Gómez". A compound surname is written in
    the `.bib` as `{Dibo Gómez, J. F.}`."""
    initials = " ".join(f"{n[0]}." for n in map(_clean, p.first_names + p.middle_names)
                        if n)
    last = _clean(" ".join(p.prelast_names + p.last_names + p.lineage_names))
    return f"{initials} {last}".strip()


def _ieee_authors(entry, strings):
    """IEEE list: "A", "A and B", "A, B, and C"; seven or more: "A et al."."""
    people = entry.persons.get("author") or entry.persons.get("editor") or []
    names = [_ieee_name(p) for p in people]
    if len(names) >= 7:
        return f"{names[0]} et al."
    if len(names) <= 2:
        return strings["and"].join(names)
    return ", ".join(names[:-1]) + strings["and_list"] + names[-1]


def _entry_url(entry):
    """The entry's link: `url`, or the `\\url{...}` (or bare URL) in
    `howpublished`, or the `doi` through doi.org. Empty string with none."""
    f = entry.fields
    url = _clean(f.get("url", ""))
    howpub = str(f.get("howpublished", "")).strip()
    if not url:
        m = _BIB_URL_RE.search(howpub)
        url = m.group(1).strip() if m else (
            howpub if howpub.startswith(("http://", "https://")) else "")
    if not url and f.get("doi"):
        url = f"https://doi.org/{_clean(f['doi'])}"
    return url


class _Quoted(str):
    """A title that goes in quotes: the comma or period after it goes inside."""


def _ieee_join(segs):
    """Join the non-empty parts with commas and end with a period."""
    out = [s for s in segs if s]
    parts = []
    for i, seg in enumerate(out):
        end = "." if i == len(out) - 1 else ","
        if isinstance(seg, _Quoted):
            parts.append(f"“{seg}{end}”")
        else:
            parts.append(seg if end == "." and seg.endswith(".") else seg + end)
    return " ".join(parts)


# The first three letters of a month in English or Spanish, as `month = oct`
# (pybtex expands it to "October"), `{octubre}` or `{10}` write it.
_MONTHS = {m: i % 12 for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec "
    "ene feb mar abr may jun jul ago sep oct nov dic".split())}


def _ieee_month(month, strings):
    """A month in its IEEE short form ("Oct."), or the text as it is."""
    key = month.strip().lower()
    i = int(key) - 1 if key.isdigit() and 1 <= int(key) <= 12 else _MONTHS.get(key[:3])
    return month if i is None else strings["months"].split()[i]


def format_ieee(entry, strings):
    """One reference in IEEE style, as HTML. A title is in quotes for an
    article, a chapter, a paper or a web page, and in italics for a book or a
    thesis; the container (journal, book, site) is in italics. With a link, the
    entry ends with "Accessed: <urldate>. [Online]. Available: <url>"."""
    f = {k.lower(): escape(_clean(v)) for k, v in entry.fields.items()}
    kind = entry.type.lower()
    title = f.get("title", "")
    em = lambda v: f"<em>{v}</em>" if v else ""  # noqa: E731
    pages = f.get("pages", "").replace("--", "–").replace("-", "–")
    pages = (f"pp. {pages}" if "–" in pages else f"p. {pages}") if pages else ""
    date = " ".join(x for x in (_ieee_month(f.get("month", ""), strings),
                                f.get("year", "")) if x)
    vol = f"vol. {f['volume']}" if f.get("volume") else ""
    num = f"{strings['no']} {f['number']}" if f.get("number") else ""
    place = ": ".join(x for x in (f.get("address", ""), f.get("publisher", "")) if x)
    authors = escape(_ieee_authors(entry, strings))
    within = f"{strings['in']} {em(f['booktitle'])}" if f.get("booktitle") else ""

    if kind == "article":
        segs = [authors, _Quoted(title), em(f.get("journal", "")), vol, num, pages, date]
    elif kind in ("inproceedings", "conference"):
        segs = [authors, _Quoted(title), within, f.get("address", ""), date, pages]
    elif kind in ("incollection", "inbook"):
        segs = [authors, _Quoted(title), within, place, date, pages]
    elif kind in ("book", "proceedings"):
        segs = [authors, em(title), place, date]
    elif kind in ("phdthesis", "mastersthesis", "thesis"):
        label = strings["ms"] if kind == "mastersthesis" else strings["phd"]
        segs = [authors, em(title), label, f.get("school", ""), f.get("address", ""), date]
    elif kind == "techreport":
        rep_no = f"{strings['techrep']} {f.get('number', '')}".strip()
        segs = [authors, _Quoted(title), f.get("institution", ""),
                f.get("address", ""), rep_no, date]
    else:   # misc, online, manual…: a web page, mostly
        howpub = f.get("howpublished", "")
        site = "" if "url" in howpub.lower() or howpub.startswith("http") else howpub
        container = (site or f.get("organization") or f.get("publisher")
                     or f.get("journal") or f.get("booktitle") or "")
        segs = [authors, _Quoted(title), em(container), date]
    text = _ieee_join(segs)

    url = _entry_url(entry)
    if url:
        accessed = escape(_clean(entry.fields.get("urldate")
                                 or entry.fields.get("accessed") or ""))
        if accessed:
            text += f" {strings['accessed']} {accessed}."
        link = f'<a class="ref-url" href="{escape(url)}">{escape(url)}</a>'
        text += f" {strings['online']} {strings['available']} {link}"
    return text


def map_prose(body_md, fn):
    """Apply `fn` to the Markdown text outside code fences and code spans."""
    out, in_fence = [], False
    for line in body_md.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
        else:
            out.append(line if in_fence else sub_prose(line, fn))
    return "\n".join(out)


def process_citations(body_md, entries, strings, base=2):
    """Replace each `[@key]` with its linked `[n]` and append the References
    section, at the document's top heading level `base`, so it is numbered and
    enters the TOC like any other section. A key missing from the `.bib` stays
    visible, with a warning."""
    number = {}           # key (lowercase) -> (number, key)

    def render_group(m):
        parts = []
        for key in _CITE_KEY_RE.findall(m.group(0)):
            if key not in entries:
                print(f"    (warning: citation '@{key}' is not in the bibliography)",
                      file=sys.stderr)
                parts.append(escape(f"[@{key}]"))
                continue
            n, _ = number.setdefault(key.lower(), (len(number) + 1, key))
            parts.append(f'[<a href="#{_slug("ref", key)}" class="cite">{n}</a>]')
        return ", ".join(parts)

    body_md = map_prose(body_md, lambda t: _CITE_GROUP_RE.sub(render_group, t))
    if not number:
        return body_md
    lines = [f'{"#" * base} {strings["references"]}', ""]
    for n, key in number.values():
        lines += [f'<p class="ref-entry" id="{_slug("ref", key)}">'
                  f'<span class="ref-num">[{n}]</span>'
                  f'{format_ieee(entries[key], strings)}</p>', ""]
    return f"{body_md}\n\n" + "\n".join(lines)


# ─────────────────────── Figure/table/code numbering ───────────────────────

def _mix(color, other, t):
    """Blend two `#rrggbb` colors: t=0 gives `color`, t=1 gives `other`. Any
    other color format is returned unchanged."""
    c, o = color.lstrip("#"), other.lstrip("#")
    if len(c) != 6 or len(o) != 6:
        return color
    rgb = [round(int(c[i:i + 2], 16) * (1 - t) + int(o[i:i + 2], 16) * t)
           for i in (0, 2, 4)]
    return "#" + "".join(f"{v:02x}" for v in rgb)


def _is_dark(color):
    c = color.lstrip("#")
    return len(c) == 6 and sum(int(c[i:i + 2], 16) for i in (0, 2, 4)) < 3 * 128


def code_file_bar(path, box):
    """The `<!-- file: path -->` bar for one code block. `box` is the block's
    HTML (the `.codehilite` div or a bare `<pre>`): the bar takes the theme's
    background and text color from its inline styles, so it matches any
    `code_theme`. The bar is a little lighter than a dark block and a little
    darker than a light one."""
    bg_m = re.search(r'background:\s*(#[0-9a-fA-F]{6})', box)
    fg_m = re.search(r'<pre[^>]*style="[^"]*color:\s*(#[0-9a-fA-F]{6})', box)
    bg = bg_m.group(1) if bg_m else "#f4f4f4"
    fg = fg_m.group(1) if fg_m else "#1a1a1a"
    bar = _mix(bg, "#ffffff" if _is_dark(bg) else "#000000", 0.08)
    dots = "".join(f'<i style="background:{c}"></i>'
                   for c in ("#ff5f57", "#febc2e", "#28c840"))
    folder, _, name = path.rpartition("/")
    folder = f'<span class="dir">{escape(folder)}/</span>' if folder else ""
    return (f'<div class="code-file" style="background:{bar};color:{fg}">'
            f'<span class="dots">{dots}</span>{folder}{escape(name)}</div>')


CAPTION_TOP_CSS = """
caption { caption-side: top; padding: 0 0 6px; }
figcaption { margin: 0 0 5px; }
.code-label { margin: 0 0 4px; }
.code-label, figcaption, caption { break-before: auto; break-after: avoid; }
"""


def resolve_caption_top(meta):
    """`caption_position`: `bottom` (default) or `top`. Warn on any other value."""
    val = (meta.get("caption_position") or "").strip().lower()
    if val in ("top", "above", "arriba", "encima"):
        return True
    if val not in ("", "bottom", "below", "abajo", "debajo"):
        print(f"    (warning: unknown caption_position '{val}'; using bottom)",
              file=sys.stderr)
    return False


# The HTML that a caption keeps: a formula, and a citation number.
_CAPTION_HTML_RE = re.compile(
    r'<span class="math">.*?</svg></span>|<a href="#ref-[^"]*" class="cite">\d+</a>',
    re.DOTALL)


def caption_html(text):
    """Escape a caption, except its formulas and citation links."""
    out, last = [], 0
    for m in _CAPTION_HTML_RE.finditer(text):
        out += [escape(text[last:m.start()]), m.group(0)]
        last = m.end()
    return "".join(out) + escape(text[last:])


# A paragraph that holds only images (2 to 4) is one figure: a row.
_IMG_ROW = r'<p>\s*<img\b[^>]*>(?:\s*<img\b[^>]*>)+\s*</p>'


def image_row(par):
    """The images of a row paragraph side by side, each with its alt text as a
    sub-caption: "(a) Before", "(b) After"."""
    cells = []
    for i, img in enumerate(re.findall(r'<img\b[^>]*>', par)):
        alt_m = re.search(r'\balt="([^"]*)"', img)
        sub = f'({chr(97 + i)}) {alt_m.group(1)}' if alt_m and alt_m.group(1) \
            else f'({chr(97 + i)})'
        cells.append(f'<div class="sub">{img}<span class="subcap">{sub}</span></div>')
    return f'<div class="row">{"".join(cells)}</div>'


def add_asset_numbers(html, strings, base=2, caption_top=False):
    """Number figures, tables, code blocks and equations (x.y, resetting on
    each top-level section — `base` is the document's own top heading level,
    see detect_base_level), add their label, and collect the data for the
    indexes.

    Returns (html, figures, tables, code_blocks, equations, missing). An
    equation takes no caption: its label is "(x.y)". `missing` lists the
    labels of the elements WITHOUT a caption: an image uses its `alt`; tables and
    code blocks require `<!-- caption: -->`. If `missing` is not empty, the
    caller refuses to generate the PDF. A `<!-- file: path -->` above a code
    block adds the file-name bar on top of it (see code_file_bar)."""
    section = [0]
    figs = [0]
    tabs = [0]
    codes = [0]
    eqs = [0]
    pending_cap = [""]
    pending_file = [""]
    figures, tables, code_blocks, equations, missing = [], [], [], [], []
    pattern = re.compile(
        r'<!--\s*(?:caption|file):\s*.*?\s*-->'
        rf'|<h{base}\b[^>]*>|<div class="math-block">|{_IMG_ROW}|<img\b[^>]*/?>|<table\b[^>]*>'
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
            m2 = re.match(r'<!--\s*(caption|file):\s*(.*?)\s*-->', tag, re.DOTALL)
            pending = pending_cap if m2.group(1) == "caption" else pending_file
            pending[0] = m2.group(2).strip()
            return ""   # remove the comment from the output
        if lo.startswith(f'<h{base}'):
            section[0] += 1
            figs[0] = tabs[0] = codes[0] = eqs[0] = 0
            pending_cap[0] = pending_file[0] = ""
            return tag
        if lo.startswith('<div class="math-block"'):
            if not section[0]:
                return tag
            eqs[0] += 1
            label = f"({section[0]}.{eqs[0]})"
            eq_id = f"eq-{section[0]}-{eqs[0]}"
            equations.append((label, "", eq_id))
            return (f'<div class="math-block" id="{eq_id}">'
                    f'<span class="eq-num">{label}</span>')
        is_row = lo.startswith('<p>')
        if is_row or lo.startswith('<img'):
            if not section[0]:
                return tag
            figs[0] += 1
            num_label = f"{strings['figure']} {section[0]}.{figs[0]}"
            if is_row and tag.count("<img") > 4:
                raise ValueError(f"{num_label} has {tag.count('<img')} images: a row holds 2 to 4")
            fig_id = f"fig-{section[0]}-{figs[0]}"
            alt_m = re.search(r'\balt="([^"]*)"', tag)
            # A row's alts are its sub-captions, so only the comment captions it.
            alt = alt_m.group(1) if alt_m and not is_row else ""
            caption = pending_cap[0] or alt
            pending_cap[0] = ""
            if not caption:
                missing.append(num_label)
            figures.append((num_label, caption, fig_id))
            cap = f'<figcaption>{caption_html(_full_label(num_label, caption))}</figcaption>'
            content = image_row(tag) if is_row else tag
            inner = cap + content if caption_top else content + cap
            cls = ' class="img-row"' if is_row else ""
            return f'<figure id="{fig_id}"{cls}>{inner}</figure>'
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
            rendered = caption_html(_full_label(num_label, caption))
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
            rendered = caption_html(_full_label(num_label, caption))
            bar = code_file_bar(pending_file[0], tag) if pending_file[0] else ""
            pending_file[0] = ""
            label = f'<p class="code-label">{rendered}</p>'
            inner = label + bar + tag if caption_top else bar + tag + label
            return f'<div class="code-block" id="{code_id}">{inner}</div>'
        return tag

    return pattern.sub(sub, html), figures, tables, code_blocks, equations, missing


_FN_LIST_RE = re.compile(r'<div class="footnote">.*?</ol>\s*</div>', re.DOTALL)
_FN_BACKREF_RE = re.compile(r'(?:&#160;)?<a class="footnote-backref"[^>]*>.*?</a>')
_FN_CALL_RE = re.compile(r'<sup id="fnref(\d*):([^"]+)">.*?</sup>')


def inline_footnotes(html):
    """Move each note of the `footnotes` extension from its list at the end to
    its first call, as a `<span class="fn">`: the CSS `float: footnote` puts the
    span at the foot of its page. A later call of the same note shows only its
    number. A note keeps its paragraphs, with a line break between them; any
    other block (a list, code) is dropped with a warning."""
    notes = {}
    for block in _FN_LIST_RE.findall(html):
        parts = re.split(r'<li id="fn:([^"]+)">', _FN_BACKREF_RE.sub("", block))
        for fid, inner in zip(parts[1::2], parts[2::2]):
            paras = [p.strip() for p in re.findall(r'<p>(.*?)</p>', inner, re.DOTALL)]
            notes[fid] = "<br>".join(p for p in paras if p)
            if re.sub(r'<p>.*?</p>|</?(?:li|ol|div)>|\s', "", inner, flags=re.DOTALL):
                print(f"    (warning: footnote '{fid}' keeps only its paragraphs)",
                      file=sys.stderr)
    html = _FN_LIST_RE.sub("", html)
    order = []

    def call(m):
        fid = m.group(2)
        if fid in order:
            return f'<sup class="fn-again">{order.index(fid) + 1}</sup>'
        order.append(fid)
        return f'<span class="fn">{notes.get(fid, "")}</span>'

    return _FN_CALL_RE.sub(call, html)


_ABBR_RE = re.compile(r'<abbr title="([^"]*)">(.*?)</abbr>')
_LINK_OR_ABBR_RE = re.compile(r'<a\b[^>]*>.*?</a>|' + _ABBR_RE.pattern, re.DOTALL)


def link_acronyms(html, link=True):
    """Turn each `<abbr>` of the `abbr` extension (`*[HTML]: definition`) into a
    link to the acronym's entry in the list of acronyms. An acronym inside a
    link stays plain text, because a link cannot hold a link. Returns (html,
    [(acronym, definition)]) with the used acronyms in alphabetical order. With
    `link=False` (no list of acronyms) every acronym stays plain text."""
    found = {}

    def plain(m):
        found[m.group(2)] = m.group(1)
        return m.group(2)

    def repl(m):
        if m.group(1) is None or not link:
            return _ABBR_RE.sub(plain, m.group(0))
        found[m.group(2)] = m.group(1)
        return f'<a class="abbr" href="#{_slug("abbr", m.group(2))}">{m.group(2)}</a>'

    html = _LINK_OR_ABBR_RE.sub(repl, html)
    return html, sorted(found.items(), key=lambda kv: kv[0].lower())


def warn_uncited(html, items, strings):
    """Warn about each figure, table, code block or equation that the text never
    cites with `[[...]]`, or that comes before its first cross-reference."""
    for num_label, _, aid in items:
        if aid.startswith("eq-"):
            num_label = f'{strings["equation"]} {num_label}'
        at = html.find(f'id="{aid}"')
        ref = html.find(f'href="#{aid}"')
        if ref < 0:
            print(f"    (warning: {num_label} is not cited in the text)",
                  file=sys.stderr)
        elif ref > at:
            print(f"    (warning: {num_label} appears before its first "
                  f"cross-reference)", file=sys.stderr)


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


def heading_css(base, page_break):
    """Page break before every top-level section, only when `page_break` is on
    (off by default). `base` is the document's own top heading level (see
    detect_base_level), so a `#`-based document breaks on `#` and a `##`-based
    one on `##`. A section that opens the body right after the title block (no
    cover, no TOC, no lists) stays on page 1 with the title."""
    if not page_break:
        return ""
    return (f".body h{base} {{ break-before: page; }}"
            f".doc-head + .body > h{base}:first-child {{ break-before: auto; }}")


def outline_css(depth, base=2):
    """`bookmark-level` rules for the PDF outline, generated from the TOC depth so
    they match it: levels `base`…`depth` are marked; deeper ones only if forced
    with `<!-- toc -->` (`toc-force`), and those marked `<!-- no-toc -->`
    (`toc-skip`) are omitted. The outline always starts at bookmark-level 1, so
    the top-level sections sit at the root whatever heading level they use."""
    lines = []
    for level in range(base, 7):
        bl = level - base + 1
        if level <= depth:
            lines.append(f".body h{level} {{ bookmark-level: {bl}; }}")
        else:
            lines.append(f".body h{level} {{ bookmark-level: none; }}")
            lines.append(f".body h{level}.toc-force {{ bookmark-level: {bl}; }}")
    lines.append(".body .toc-skip { bookmark-level: none; }")
    return "\n".join(lines)


def _indices_html(figures, tables, code_blocks, strings, acronyms, meta):
    """Build the indexes section (figures, tables, code blocks, acronyms) for
    the non-empty ones whose key (`figure_index`, `table_index`…) is not off."""
    on = lambda key: _truthy(meta[key])

    def _block(title, rows):
        items = "\n".join(f'    <li>{r}</li>' for r in rows)
        return (
            f'<div class="idx-block">\n  <h2>{title}</h2>\n'
            f'  <ul class="doc-index">\n{items}\n  </ul>\n</div>\n'
        )

    def _row(num_label, caption, anchor_id):
        cap = f": {caption_html(caption)}" if caption else ""
        return (f'<a href="#{anchor_id}">'
                f'<span class="idx-label">{escape(num_label)}</span>{cap}</a>')

    parts = []
    for items, key, flag in ((figures, "idx_figures", "figure_index"),
                             (tables, "idx_tables", "table_index"),
                             (code_blocks, "idx_code", "code_index")):
        if items and on(flag):
            rows = [_row(nl, cap, aid) for nl, cap, aid in items]
            parts.append(_block(strings[key], rows))
    if acronyms and on("acronym_index"):
        rows = "".join(f'<dt id="{_slug("abbr", t)}">{t}</dt><dd>{d}</dd>'
                       for t, d in acronyms)
        parts.append(f'<div class="idx-block">\n  <h2>{strings["idx_abbr"]}</h2>\n'
                     f'  <dl class="abbr-list">{rows}</dl>\n</div>\n')
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


def doc_head_html(meta, strings):
    """Title block at the top of page 1 when the document has no cover: title,
    subtitle, comment and author, with no logo."""
    lines = [("doc-title", meta["title"]), ("subtitle", meta["subtitle"]),
             ("meta-line", meta["comment"]),
             ("author", meta["author"] and f'{strings["by"]} {meta["author"]}')]
    tags = "".join(f'<p class="{c}">{escape(t)}</p>' for c, t in lines if t)
    return f'<header class="doc-head">{tags}</header>\n' if tags else ""


def content_html(meta, body_md, strings, code_style, page_size, bib_entries=None):
    """TOC + indexes + body in a single HTML. Raises ValueError if any element
    lacks a caption."""
    # The document's own top heading level: `#` when the title comes from the
    # front matter, `##` in the older convention where `#` was the title.
    # Numbering, the TOC, the outline, the per-section page break and the
    # figure/table numbering are all measured from it.
    base = detect_base_level(body_md)
    # The TocExtension captures every level (1-6); the real TOC depth (toc_depth)
    # and the individual marks are applied later when building the TOC from
    # `md.toc_tokens`. `attr_list` lets us inject the `toc-force` / `toc-skip`
    # classes from the `<!-- toc -->` comments.
    md = markdown.Markdown(
        # tab_length=2 lets nested lists use the common 2-space indentation
        # (Python-Markdown defaults to 4); sane_lists keeps an ordered list
        # that follows an unordered one as a separate <ol> instead of merging
        # them into one <ul> (which rendered the numbers as bullets).
        tab_length=2,
        extensions=[TocExtension(toc_depth="1-6"), "tables", "fenced_code",
                    "codehilite", "attr_list", "sane_lists", "footnotes", "abbr"],
        extension_configs={"codehilite": {
            "noclasses": True, "guess_lang": False, "pygments_style": code_style,
            "prestyles": f"color:{_style_fg(code_style)}",
            "filters": [_yaml_scalars()],
            # PHP: highlight a snippet with no `<?php` tag (other lexers ignore it).
            "startinline": True}},
    )
    # Citations become numbers and links, and the references go at the end:
    # the reference list is a section, so it gets numbered and enters the TOC.
    if bib_entries:
        body_md = process_citations(body_md, bib_entries, strings, base)
    # Individual TOC marks (`<!-- toc -->` / `<!-- no-toc -->`): translated into
    # classes before numbering and converting (they work whether numbering is on
    # or off).
    body_md = apply_toc_markers(body_md)
    # Automatic section numbering (on by default): applied to the Markdown before
    # converting, so the number is reflected in the body, the TOC, and the
    # outline. Disabled with `numbering: false`.
    if _truthy(meta.get("numbering")):
        body_md = apply_section_numbering(body_md, base)
    # Blocks with their own theme are highlighted separately and re-injected after
    # conversion; the rest use the document-wide theme (code_style) via codehilite.
    body_md, themed_blocks = extract_themed_blocks(yml_fences(body_md))
    body_md, formulas, formula_sources = extract_math(body_md)
    body = md.convert(body_md)
    toc_tokens = md.toc_tokens

    def unmark(tokens):
        for tok in tokens:
            for marker, latex in formula_sources.items():
                tok["name"] = tok["name"].replace(marker, latex)
            unmark(tok.get("children", []))
    unmark(toc_tokens)
    for token, snippet in (*themed_blocks.items(), *formulas.items()):
        body = body.replace(f"<p>{token}</p>", snippet).replace(token, snippet)
    body = inline_footnotes(body)

    # Table of contents: default depth (toc_depth) + individual marks collected
    # from the classes apply_toc_markers left on the headings of the converted
    # body.
    toc_depth = resolve_toc_depth(meta)
    force_ids, skip_ids = collect_toc_overrides(body)
    toc_tree = build_toc_html(toc_tokens, toc_depth, force_ids, skip_ids)

    caption_top = resolve_caption_top(meta)
    body, figures, tables, code_blocks, equations, missing = add_asset_numbers(
        body, strings, base, caption_top)
    if missing:
        raise ValueError(
            "elements without a caption (add <!-- caption: ... --> or an alt): "
            + ", ".join(missing)
        )
    body = resolve_cross_refs(body, figures, tables, code_blocks, equations)
    warn_uncited(body, (*figures, *tables, *code_blocks, *equations), strings)
    body = apply_keep_with_prev(body)
    body, acronyms = link_acronyms(body, _truthy(meta["acronym_index"]))
    indices = _indices_html(figures, tables, code_blocks, strings, acronyms, meta)
    toc_page = (f'<div class="toc-page">\n  <h2>{strings["toc"]}</h2>\n  {toc_tree}\n</div>\n'
                if _truthy(meta["toc"]) else "")
    # Without a cover, page 1 opens with the title block, and its page header
    # stays empty so the title does not appear twice.
    head = "" if _truthy(meta["cover"]) else doc_head_html(meta, strings)
    first_css = ("" if _truthy(meta["cover"])
                 else "@page :first { @top-center { content: none; } }")
    lang = meta.get("lang", "es")

    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head><meta charset="utf-8">
<style>{page_css(meta, strings, page_size)}{font_face_css()}{BASE_CSS}{font_size_css(meta)}{toc_size_css(meta)}{heading_css(base, _truthy(meta.get("page_break")))}{outline_css(toc_depth, base)}{CAPTION_TOP_CSS if caption_top else ""}{first_css}</style>
</head>
<body>
{head}{toc_page}{indices}<main class="body">{body}</main>
</body>
</html>"""


# ─────────────────────────── Assembly ───────────────────────────

def merge_pdfs(cover_bytes, content_bytes, meta):
    """Prepend the cover to the content, preserving the outline and internal links
    (pypdf re-adjusts the pages), and write the document metadata."""
    writer = pypdf.PdfWriter()
    if cover_bytes:
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


# ─────────────────────── Tables wider than the text ───────────────────────
# A column that cannot wrap (a long identifier in `code`) makes a table wider than
# the text block, and the table then spills past the right margin only. CSS cannot
# measure that, so the page is laid out, each overflowing table is measured, and the
# table gets an inline style. First choice: shrink its text to fit, down to
# TABLE_MIN_PT. If that is not enough, keep that size and centre the table, with the
# same overhang on both sides, as far as TABLE_GUTTER_PX from the page edge. A table
# that does not fit even then is left alone and reported.
TABLE_MIN_PT = 9
TABLE_GUTTER_PX = 19  # 0.5 cm
_TABLE_TAG = re.compile(r"<table(?=[\s>])")


def _measure_tables(doc):
    """{n: {...}} for each `<table data-fit="n">` wider than its container: the
    border-box width `need`, the container's `avail` width and left edge `cx`,
    the page width and the table's font size, all in px."""
    found = {}

    def first_row_fixed(box):
        # Width that does not shrink with the font: cell padding and borders.
        for b in box.descendants():
            if type(b).__name__ == "TableRowBox":
                return sum(c.padding_left + c.padding_right + c.border_left_width
                           + c.border_right_width for c in b.children)
        return 0

    def walk(box, up, page_w):
        if type(box).__name__ == "TableBox" and box.element.get("data-fit"):
            container = up[-2]
            need = box.border_width()
            if need > container.width + 0.5:
                n = int(box.element.get("data-fit"))
                t = found.setdefault(n, {"need": 0})
                t.update(avail=container.width, cx=container.content_box_x(),
                         page_w=page_w, font=box.style["font_size"],
                         fixed=first_row_fixed(box))
                t["need"] = max(t["need"], need)
        for child in getattr(box, "children", ()):
            walk(child, up + [box], page_w)

    for page in doc.pages:
        box = page._page_box
        walk(box, [box], box.margin_width())
    return found


def fit_wide_tables(html, base_url):
    """Lay out `html` and return the weasyprint Document, with every table that
    overflows its text block shrunk or centred as described above."""
    counter = iter(range(1_000_000))
    html = _TABLE_TAG.sub(lambda m: f'<table data-fit="{next(counter)}"', html)
    styles, done, floored = {}, set(), set()

    def render():
        def tag(m):
            css = "; ".join(f"{k}: {v}" for k, v in styles.get(int(m.group(1)), {}).items())
            return f'<table data-fit="{m.group(1)}"' + (f' style="{css}"' if css else "")
        return weasyprint.HTML(
            string=re.sub(r'<table data-fit="(\d+)"', tag, html),
            base_url=base_url).render()

    for attempt in range(4):
        doc = render()
        todo = {n: t for n, t in _measure_tables(doc).items() if n not in done}
        if not todo:
            return doc
        for n, t in todo.items():
            if attempt == 3:
                print(f"    (warning: table {n + 1} is still wider than the text)",
                      file=sys.stderr)
                continue
            floor = TABLE_MIN_PT * 96 / 72
            # Only the text shrinks with the font, so scale just that part.
            fit = t["font"] * (t["avail"] - t["fixed"]) / (t["need"] - t["fixed"]) * 0.99
            if t["fixed"] < t["avail"] and fit >= floor:
                styles[n] = {"font-size": f"{fit:.2f}px"}
            elif n not in floored:
                floored.add(n)  # shrink to the floor, then measure what is left
                styles[n] = {"font-size": f"{floor:.2f}px"}
            else:
                over = t["need"] - t["avail"]
                done.add(n)
                if (t["cx"] - over / 2 >= TABLE_GUTTER_PX
                        and t["cx"] + t["avail"] + over / 2 <= t["page_w"] - TABLE_GUTTER_PX):
                    styles[n]["margin-left"] = f"-{over / 2:.2f}px"
                else:
                    styles.pop(n)
                    print(f"    (warning: table {n + 1} is wider than the page and "
                          f"cannot be fitted; split its columns or rotate it)",
                          file=sys.stderr)
    return doc


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
    html = content_html(meta, body_md, strings, code_style, page_size, bib_entries)
    content_pdf = fit_wide_tables(html, base_url).write_pdf()
    cover_pdf = (weasyprint.HTML(
        string=cover_html(meta, logo_uri, strings, page_size),
        base_url=base_url).write_pdf() if _truthy(meta["cover"]) else None)

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


USAGE = """Usage: md-to-pdf [--watch] [-o output.pdf] <file.md | directory> ...

Converts each Markdown file to a PDF next to it, with the same name.

Options:
  -o, --output FILE  name or path of the PDF (only with a single .md)
  -w, --watch        rebuild the PDF on every save (Ctrl-C to stop)
  -h, --help         show this help"""


def main():
    watch = False
    output = None
    args = []
    rest = sys.argv[1:]
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in ("--help", "-h"):
            print(USAGE)
            return
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
        print(USAGE)
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
