#!/usr/bin/env python3
"""
MD → PDF via Chrome DevTools Protocol.
Uso: python3 md_to_pdf.py          (convierte todos los .md del directorio actual)
     python3 md_to_pdf.py f1.md f2.md ...  (convierte los archivos indicados)

Genera un único HTML (portada + índice clickable + contenido) → un PDF.
Requiere: google-chrome, python-markdown, websocket-client
"""
import subprocess
import time
import json
import base64
import urllib.request
import tempfile
import os
import sys
import io
import shutil
import socket
import re
from html import escape
import markdown
from markdown.extensions.toc import TocExtension
import websocket
import pypdf
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import inch
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

LOGO_NAMES = ["logo_uja.webp", "logo_uja.png", "logo.webp", "logo.png"]
SCRIPT_DIR = Path(__file__).resolve().parent
FONTS_DIR = SCRIPT_DIR / "fonts"
IS_WINDOWS = sys.platform.startswith("win")

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
        "year":        "Curso",
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
        "year":        "Year",
    },
}


def get_strings(lang):
    return STRINGS.get(lang, STRINGS["es"])


def find_chrome():
    """Localiza el binario de Chrome/Chromium en Windows o Linux."""
    names = (
        ["chrome", "chrome.exe"]
        if IS_WINDOWS
        else ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]
    )
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if IS_WINDOWS:
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
            base = os.environ.get(env)
            if base:
                cand = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
                if cand.exists():
                    return str(cand)
    return None


def font_face_css():
    serif_reg  = FONTS_DIR / "SourceSerif4-VariableFont_opsz,wght.ttf"
    serif_ita  = FONTS_DIR / "SourceSerif4-Italic-VariableFont_opsz,wght.ttf"
    grotesk    = FONTS_DIR / "Space_Grotesk" / "SpaceGrotesk-VariableFont_wght.ttf"
    mono_reg   = FONTS_DIR / "Space_Mono" / "SpaceMono-Regular.ttf"
    mono_ita   = FONTS_DIR / "Space_Mono" / "SpaceMono-Italic.ttf"
    mono_bold  = FONTS_DIR / "Space_Mono" / "SpaceMono-Bold.ttf"
    mono_bita  = FONTS_DIR / "Space_Mono" / "SpaceMono-BoldItalic.ttf"
    rules = ""
    if serif_reg.exists():
        rules += f"""
@font-face {{
  font-family: 'Source Serif 4';
  src: url('{serif_reg.as_uri()}') format('truetype');
  font-weight: 100 900;
  font-style: normal;
}}"""
    if serif_ita.exists():
        rules += f"""
@font-face {{
  font-family: 'Source Serif 4';
  src: url('{serif_ita.as_uri()}') format('truetype');
  font-weight: 100 900;
  font-style: italic;
}}"""
    if grotesk.exists():
        rules += f"""
@font-face {{
  font-family: 'Space Grotesk';
  src: url('{grotesk.as_uri()}') format('truetype');
  font-weight: 300 700;
  font-style: normal;
}}"""
    if mono_reg.exists():
        rules += f"""
@font-face {{
  font-family: 'Space Mono';
  src: url('{mono_reg.as_uri()}') format('truetype');
  font-weight: 400;
  font-style: normal;
}}"""
    if mono_ita.exists():
        rules += f"""
@font-face {{
  font-family: 'Space Mono';
  src: url('{mono_ita.as_uri()}') format('truetype');
  font-weight: 400;
  font-style: italic;
}}"""
    if mono_bold.exists():
        rules += f"""
@font-face {{
  font-family: 'Space Mono';
  src: url('{mono_bold.as_uri()}') format('truetype');
  font-weight: 700;
  font-style: normal;
}}"""
    if mono_bita.exists():
        rules += f"""
@font-face {{
  font-family: 'Space Mono';
  src: url('{mono_bita.as_uri()}') format('truetype');
  font-weight: 700;
  font-style: italic;
}}"""
    return rules


CSS = """
html, body {
    margin: 0;
    padding: 0;
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 13pt;
    line-height: 1.6;
    color: #1a1a1a;
}

/* ── Portada ── */
.cover {
    height: 100vh;
    box-sizing: border-box;
    padding: 2.5cm 2cm;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    text-align: center;
    font-family: 'Source Serif 4', Georgia, serif;
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
.cover .subtitle   { font-size: 15.5pt; font-style: italic; color: #444; margin: 0 0 6px 0; }
.cover .meta-line  { font-size: 12pt; color: #555; margin: 3px 0; }
.cover .logo       { width: 180px; height: 180px; object-fit: contain; margin: 40px 0; }
.cover .author     { font-size: 13pt; font-style: italic; color: #333; padding-bottom: 1cm; }

/* ── Índice ── */
.toc-page { page-break-after: always; font-family: 'Source Serif 4', Georgia, serif; }
.toc-page h2 {
    font-family: 'Space Grotesk', Arial, sans-serif;
    font-size: 17.5pt;
    margin-bottom: 20px;
}
.toc-page .toc { margin: 0; padding: 0; }
.toc-page .toc ul { list-style: none; margin: 0; padding: 0; }
.toc-page .toc li { padding: 5px 0; }
.toc-page .toc li li { padding-left: 2em; font-size: 12.5pt; font-weight: normal; }
.toc-page .toc > ul > li { font-size: 13.5pt; font-weight: bold; }
.toc-page .toc a { text-decoration: none; color: #5a8fc4; }
.toc-page .toc a:hover { text-decoration: underline; }

/* ── Contenido ── */
a { color: #5a8fc4; }
h1, h2, h3 { font-family: 'Space Grotesk', Arial, sans-serif; }
h1 { font-size: 23.5pt; margin-bottom: 16px; }
/* Cada sección de nivel ## empieza en página nueva (salvo la primera, para no
   dejar una página en blanco tras el índice). Las subsecciones ### no rompen. */
h2:not(:first-of-type) { page-break-before: always; }
h2 { font-size: 17.5pt; margin-top: 28px; }
h3 { font-size: 14pt; margin-top: 20px; color: #222; }
code {
    font-family: 'Space Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace;
    background: #f4f4f4;
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 11pt;
}
pre {
    font-family: 'Space Mono', 'DejaVu Sans Mono', 'Liberation Mono', monospace;
    background: #f4f4f4;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 12px;
    font-size: 10.5pt;
    line-height: 1.4;
    page-break-inside: avoid;  /* no partir bloques de código entre páginas */
}
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12pt; page-break-inside: avoid; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
th { background: #e8e8e8; font-weight: bold; }
blockquote {
    border-left: 4px solid #aaa;
    margin: 12px 0;
    padding: 4px 16px;
    color: #555;
    background: #fafafa;
}
hr { border: none; margin: 28px 0; }
ul, ol { margin: 6px 0; padding-left: 2em; }
li { margin: 0; }
li > p { margin: 0; padding: 0; }
figure { margin: 14px auto; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
figcaption { font-size: 11pt; color: #555; margin-top: 5px; font-style: italic; }
caption { caption-side: bottom; font-size: 11pt; color: #555; padding-top: 6px; font-style: italic; text-align: center; }
.code-block { margin: 12px 0; page-break-inside: avoid; }
.code-block > pre, .code-block > .codehilite { margin: 0; }
.code-label { font-size: 11pt; color: #555; margin: 4px 0 0; font-style: italic; text-align: center; }
.indices-section { page-break-after: always; font-family: 'Source Serif 4', Georgia, serif; }
.idx-block { margin-bottom: 32px; }
.idx-block h2 { font-family: 'Space Grotesk', Arial, sans-serif; font-size: 17.5pt; margin-bottom: 16px; }
.doc-index { list-style: none; margin: 0; padding: 0; }
.doc-index li { padding: 5px 0; border-bottom: 1px dotted #ddd; font-size: 13pt; }
.doc-index a { text-decoration: none; color: #5a8fc4; }
.idx-label { font-weight: bold; min-width: 7em; display: inline-block; }
"""

DEBUG_PORT = 9333  # por defecto; main() escoge un puerto libre real al arrancar


def _free_port():
    """Pide al SO un puerto TCP libre para el remote-debugging de Chrome (evita
    choques si quedó un Chrome colgado en un puerto fijo o si se lanzan dos
    conversiones a la vez)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_chrome(timeout=10):
    for _ in range(timeout * 10):
        try:
            urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=1)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def cdp_session(ws_url):
    ws = websocket.WebSocket()
    ws.connect(ws_url, timeout=10)
    _id = [0]

    def send(method, params=None):
        _id[0] += 1
        ws.send(json.dumps({"id": _id[0], "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == _id[0]:
                if "error" in msg:
                    raise RuntimeError(f"CDP error: {msg['error']}")
                return msg

    def wait_event(event_name, timeout=10):
        ws.settimeout(timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = json.loads(ws.recv())
                if msg.get("method") == event_name:
                    return msg
            except websocket.WebSocketTimeoutException:
                break
        ws.settimeout(None)

    return ws, send, wait_event


def extract_meta(md_text):
    meta = {"title": "", "subject": "", "author": "", "master": "", "curso": "", "lang": "es"}
    keys = {
        "**Asignatura:**": "subject",
        "**Autor:**":      "author",
        "**Máster":        "master",
        "**Curso:**":      "curso",
        "**Language:**":   "lang",
        "**Idioma:**":     "lang",
    }
    for line in md_text.splitlines():
        s = line.strip()
        if not meta["title"] and line.startswith("# "):
            meta["title"] = line[2:].strip()
        for prefix, key in keys.items():
            if not meta[key] and s.startswith(prefix):
                meta[key] = s.split(":**", 1)[-1].strip().strip("*").strip()
    return meta


def find_logo(md_path):
    for name in LOGO_NAMES:
        for d in (md_path.parent, SCRIPT_DIR):
            logo = d / name
            if logo.exists():
                data = logo.read_bytes()
                ext = logo.suffix.lstrip(".")
                mime = "image/webp" if ext == "webp" else f"image/{ext}"
                return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return None


def cover_html(meta, logo_uri, strings):
    """Portada standalone — se renderiza sin header/footer. Los metadatos se
    escapan como HTML para que un '&', '<' o '>' en el título/autor no rompa la
    página (el cuerpo ya lo escapa markdown; la cabecera/pie son texto plano)."""
    title   = escape(meta["title"])
    subject = escape(meta["subject"])
    author  = escape(meta["author"])
    lang    = meta.get("lang", "es")
    logo_tag = f'<img class="logo" src="{logo_uri}" alt="Logo">' if logo_uri else ""
    master_line = f'<p class="meta-line">{escape(meta["master"])}</p>' if meta["master"] else ""
    curso_line  = (
        f'<p class="meta-line">{escape(strings["year"])} {escape(meta["curso"])}</p>'
        if meta["curso"] else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <style>@page {{ margin: 0; }}{font_face_css()}{CSS}</style>
</head>
<body>
<div class="cover">
  <div class="top">
    <h1>{title}</h1>
    <p class="subtitle">{subject}</p>
    {master_line}
    {curso_line}
    {logo_tag}
  </div>
  <p class="author">{escape(strings["by"])} {author}</p>
</div>
</body>
</html>"""


def toc_content_html(meta, md_text, md_dir, strings):
    """Índice + contenido en un único HTML para que los links anchor funcionen.
    Devuelve (html, toc_tokens); toc_tokens es el árbol de encabezados (nivel,
    id, nombre, hijos) que usamos para construir el marcador/outline del PDF.
    md_dir se inyecta como <base href> para que las imágenes con ruta relativa
    se resuelvan correctamente aunque el HTML se renderice desde /tmp/."""
    parts = md_text.split("\n---\n", 1)
    body_md = parts[1] if len(parts) > 1 else md_text

    md = markdown.Markdown(
        extensions=[TocExtension(toc_depth="2-3"), "tables", "fenced_code", "codehilite"],
        extension_configs={"codehilite": {"noclasses": True, "guess_lang": False}},
    )
    content_body = md.convert(body_md)
    toc_tree = md.toc
    toc_tokens = md.toc_tokens

    content_body, figures, tables, code_blocks = add_figure_table_numbers(content_body, strings)
    indices = _all_indices_html(figures, tables, code_blocks, strings)
    lang = meta.get("lang", "es")
    base_uri = md_dir.as_uri() + "/"
    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <base href="{base_uri}">
  <style>@page {{ margin: 1.15in 0.85in 0.95in 0.85in; }}{font_face_css()}{CSS}</style>
</head>
<body>
<div class="toc-page">
  <h2>{strings["toc"]}</h2>
  {toc_tree}
</div>
{indices}{content_body}
</body>
</html>"""
    return html, toc_tokens


def add_figure_table_numbers(html, strings):
    """Returns (processed_html, figures, tables, code_blocks).
    figures:     [(label, alt_text, anchor_id), ...]
    tables:      [(label, anchor_id), ...]
    code_blocks: [(label, anchor_id), ...]
    All counters reset on each <h2> section.
    Code blocks are matched as full elements (DOTALL) so inner <pre> tags
    inside a codehilite div are never double-counted."""
    section = [0]
    figs = [0]
    tabs = [0]
    codes = [0]
    figures = []
    tables = []
    code_blocks = []
    pattern = re.compile(
        r'<h2\b[^>]*>|<img\b[^>]*/?>|<table\b[^>]*>'
        r'|<div[^>]*\bclass="codehilite"[^>]*>.*?</div>'
        r'|<pre\b[^>]*>.*?</pre>',
        re.DOTALL,
    )

    def sub(m):
        tag = m.group(0)
        lo = tag.lower()
        if lo.startswith('<h2'):
            section[0] += 1
            figs[0] = 0
            tabs[0] = 0
            codes[0] = 0
            return tag
        if lo.startswith('<img'):
            if not section[0]:
                return tag
            figs[0] += 1
            label = f"{strings['figure']} {section[0]}.{figs[0]}"
            fig_id = f"fig-{section[0]}-{figs[0]}"
            alt_m = re.search(r'\balt="([^"]*)"', tag)
            alt = alt_m.group(1) if alt_m else ""
            figures.append((label, alt, fig_id))
            return f'<figure id="{fig_id}">{tag}<figcaption>{label}</figcaption></figure>'
        if lo.startswith('<table'):
            if not section[0]:
                return tag
            tabs[0] += 1
            label = f"{strings['table']} {section[0]}.{tabs[0]}"
            tab_id = f"tab-{section[0]}-{tabs[0]}"
            tables.append((label, tab_id))
            new_tag = tag[:-1] + f' id="{tab_id}">'
            return f'{new_tag}<caption>{label}</caption>'
        if lo.startswith('<div') or lo.startswith('<pre'):
            if not section[0]:
                return tag
            codes[0] += 1
            label = f"{strings['code_block']} {section[0]}.{codes[0]}"
            code_id = f"code-{section[0]}-{codes[0]}"
            code_blocks.append((label, code_id))
            return f'<div class="code-block" id="{code_id}">{tag}<p class="code-label">{label}</p></div>'
        return tag

    return pattern.sub(sub, html), figures, tables, code_blocks


def _all_indices_html(figures, tables, code_blocks, strings):
    """Build a single indices section containing all non-empty indices.
    All indices flow together so they share pages when they fit, with a
    single page-break-after on the wrapping container."""

    def _block(title, rows):
        items = "\n".join(f'    <li>{r}</li>' for r in rows)
        return (
            f'<div class="idx-block">\n'
            f'  <h2>{title}</h2>\n'
            f'  <ul class="doc-index">\n{items}\n  </ul>\n'
            f'</div>\n'
        )

    parts = []
    if figures:
        rows = [
            '<a href="#{}">'
            '<span class="idx-label">{}</span>{}</a>'.format(
                fig_id,
                escape(label),
                f" — {escape(alt)}" if alt else "",
            )
            for label, alt, fig_id in figures
        ]
        parts.append(_block(strings["idx_figures"], rows))
    if tables:
        rows = [
            f'<a href="#{tab_id}"><span class="idx-label">{escape(label)}</span></a>'
            for label, tab_id in tables
        ]
        parts.append(_block(strings["idx_tables"], rows))
    if code_blocks:
        rows = [
            f'<a href="#{code_id}"><span class="idx-label">{escape(label)}</span></a>'
            for label, code_id in code_blocks
        ]
        parts.append(_block(strings["idx_code"], rows))

    if not parts:
        return ""
    return f'<div class="indices-section">\n{"".join(parts)}</div>\n'


HF_FONT = "SpaceGroteskHF"
_hf_font_ready = None


def register_hf_font():
    """Registra Space Grotesk en reportlab para dibujar cabecera/pie. Chrome
    renderiza su cabecera/pie en un contexto aislado que ignora @font-face y solo
    usa fuentes del sistema (distinto en Windows y Linux), así que en su lugar las
    pintamos nosotros como una capa PDF con la fuente embebida: idéntico en ambos
    sistemas y sin instalar nada. Devuelve el nombre de fuente a usar."""
    global _hf_font_ready
    if _hf_font_ready is not None:
        return _hf_font_ready
    for cand in (
        FONTS_DIR / "Space_Grotesk" / "static" / "SpaceGrotesk-Medium.ttf",
        FONTS_DIR / "Space_Grotesk" / "static" / "SpaceGrotesk-Regular.ttf",
        FONTS_DIR / "Space_Grotesk" / "SpaceGrotesk-VariableFont_wght.ttf",
    ):
        if cand.exists():
            pdfmetrics.registerFont(TTFont(HF_FONT, str(cand)))
            _hf_font_ready = HF_FONT
            return HF_FONT
    _hf_font_ready = "Helvetica"  # respaldo si faltara la fuente
    return _hf_font_ready


def _fit_text(text, font, size, max_w):
    """Recorta `text` con una elipsis si su anchura supera `max_w` puntos, para
    que la cabecera/pie no se salgan de los márgenes con títulos largos."""
    if not text or pdfmetrics.stringWidth(text, font, size) <= max_w:
        return text
    ell = "…"
    while text and pdfmetrics.stringWidth(text + ell, font, size) > max_w:
        text = text[:-1]
    return text.rstrip() + ell if text else ell


def header_footer_overlay(meta, num_pages, paper_w=8.27, paper_h=11.69, side_margin=0.85):
    """Genera un PDF de `num_pages` páginas con la cabecera (título · asignatura)
    y el pie (autor centrado, 'n / total' a la derecha) para superponer al
    contenido. Tamaños en pulgadas, igual que printToPDF."""
    font = register_hf_font()
    pw, ph = paper_w * inch, paper_h * inch
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    header_text = " · ".join(filter(None, [meta["title"], meta["subject"]]))
    author = meta["author"]
    avail = pw - 2 * side_margin * inch
    header_text = _fit_text(header_text, font, 9.5, avail)
    author = _fit_text(author, font, 9.5, avail - 1.2 * inch)  # deja sitio al "n / total"
    for i in range(1, num_pages + 1):
        c.setFont(font, 9.5)
        c.setFillColorRGB(0.4, 0.4, 0.4)  # ~#666
        if header_text:
            c.drawCentredString(pw / 2, ph - 0.75 * inch, header_text)
        if author:
            c.drawCentredString(pw / 2, 0.55 * inch, author)
        c.drawRightString(pw - side_margin * inch, 0.55 * inch, f"{i} / {num_pages}")
        c.showPage()
    c.save()
    buf.seek(0)
    return buf


def add_outline(writer, content_bytes, first_content, toc_tokens):
    """Crea el outline (marcadores) del PDF a partir del árbol de encabezados,
    mapeando cada id a su página vía los destinos con nombre del contenido. Así
    el visor muestra la estructura del documento en su panel lateral."""
    if not toc_tokens:
        return
    reader = pypdf.PdfReader(io.BytesIO(content_bytes))
    id_to_page = {}
    for name, dest in reader.named_destinations.items():
        try:
            pno = reader.get_destination_page_number(dest)
        except Exception:
            pno = None
        if pno is not None:
            id_to_page[str(name).lstrip("/")] = first_content + pno

    def walk(tokens, parent):
        for t in tokens:
            title = (t.get("name") or t.get("id") or "").strip()
            page = id_to_page.get(t.get("id", ""))
            if title and page is not None:
                item = writer.add_outline_item(title, page, parent=parent)
            else:
                item = parent  # sin destino: cuelga los hijos del nivel actual
            walk(t.get("children", []), item)

    walk(toc_tokens, None)


def assemble_pdf(cover_bytes, content_bytes, meta, toc_tokens=None):
    """Une portada + contenido, estampa cabecera/pie solo en las páginas de
    contenido y añade el outline. Usa append() (no add_page) para conservar los
    enlaces internos del índice; el estampado por merge_page no toca esos destinos."""
    writer = pypdf.PdfWriter()
    writer.append(io.BytesIO(cover_bytes))
    first_content = len(writer.pages)
    writer.append(io.BytesIO(content_bytes))

    content_pages = writer.pages[first_content:]
    overlay = pypdf.PdfReader(header_footer_overlay(meta, len(content_pages)))
    for page, ov in zip(content_pages, overlay.pages):
        page.merge_page(ov)

    # merge_page deja objetos repetidos por página; deduplicar recorta algo el PDF.
    try:
        writer.compress_identical_objects()
    except Exception:
        pass

    add_outline(writer, content_bytes, first_content, toc_tokens)

    info = {tag: val for tag, val in (
        ("/Title", meta.get("title")),
        ("/Author", meta.get("author")),
        ("/Subject", meta.get("subject")),
    ) if val}
    if info:
        try:
            writer.add_metadata(info)
        except Exception:
            pass

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_render(send, wait_event):
    """Devuelve la función que renderiza un HTML a PDF vía Chrome (printToPDF).
    Se crea una sola vez por sesión, no por archivo."""
    def render(html, *, margin_top, margin_bottom, margin_lr):
        # La cabecera/pie ya no las dibuja Chrome (las estampamos después con
        # reportlab), pero dejamos márgenes arriba/abajo para que entren.
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as f:
            f.write(html)
            tmp = f.name
        try:
            send("Page.enable", {})
            send("Page.navigate", {"url": Path(tmp).resolve().as_uri()})
            wait_event("Page.loadEventFired", timeout=10)
            # Esperar a que las webfonts estén listas (en vez de un sleep fijo):
            # evita carreras de carga de fuentes que daban fallbacks erróneos.
            try:
                send("Runtime.evaluate", {
                    "expression": "document.fonts.ready.then(() => true)",
                    "awaitPromise": True,
                    "returnByValue": True,
                })
            except Exception:
                time.sleep(0.3)
            time.sleep(0.1)  # pequeño margen para el reflow tras aplicar fuentes
            result = send("Page.printToPDF", {
                "printBackground": True,
                "displayHeaderFooter": False,
                "marginTop": margin_top,
                "marginBottom": margin_bottom,
                "marginLeft": margin_lr,
                "marginRight": margin_lr,
                "paperWidth": 8.27,
                "paperHeight": 11.69,
            })
            return base64.b64decode(result["result"]["data"])
        finally:
            os.unlink(tmp)
    return render


def convert_one(md_path, render):
    """Convierte un único .md a .pdf junto a él. Lanza excepción si algo falla."""
    pdf_path = md_path.with_suffix(".pdf")
    md_text = md_path.read_text(encoding="utf-8")
    meta = extract_meta(md_text)
    strings = get_strings(meta["lang"])
    logo_uri = find_logo(md_path)

    content_html, toc_tokens = toc_content_html(meta, md_text, md_path.resolve().parent, strings)
    cover_bytes   = render(cover_html(meta, logo_uri, strings),
                           margin_top=0, margin_bottom=0, margin_lr=0)
    content_bytes = render(content_html,
                           margin_top=1.15, margin_bottom=0.95, margin_lr=0.85)

    pdf_bytes = assemble_pdf(cover_bytes, content_bytes, meta, toc_tokens)
    pdf_path.write_bytes(pdf_bytes)
    return len(pdf_bytes)


def main():
    global DEBUG_PORT

    if len(sys.argv) > 1:
        md_files = [Path(p) for p in sys.argv[1:]]
    else:
        md_files = sorted(Path(".").glob("*.md"))

    if not md_files:
        print("No hay archivos .md")
        sys.exit(1)

    chrome_bin = find_chrome()
    if not chrome_bin:
        print("No se encontró Chrome/Chromium. Instálalo o añádelo al PATH.")
        sys.exit(1)

    DEBUG_PORT = _free_port()
    chrome = subprocess.Popen(
        [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            f"--remote-debugging-port={DEBUG_PORT}",
            "--remote-allow-origins=*",
            "--disable-extensions",
            "--disable-features=site-per-process",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ,
    )

    if not wait_for_chrome():
        print("Chrome no arrancó a tiempo")
        chrome.terminate()
        sys.exit(1)

    failures = 0
    try:
        targets = json.loads(
            urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json").read()
        )
        page_target = next(t for t in targets if t["type"] == "page")
        ws, send, wait_event = cdp_session(page_target["webSocketDebuggerUrl"])
        render = make_render(send, wait_event)

        for md_path in md_files:
            pdf_path = md_path.with_suffix(".pdf")
            print(f"  {md_path.name} → {pdf_path.name}", end=" ", flush=True)
            try:
                kb = convert_one(md_path, render) // 1024
                print(f"[OK, {kb} KB]")
            except Exception as e:
                failures += 1
                print(f"[ERROR: {e}]")

        ws.close()
    finally:
        chrome.terminate()
        chrome.wait()

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
