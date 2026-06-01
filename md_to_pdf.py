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
import markdown
from markdown.extensions.toc import TocExtension
import websocket
import pypdf
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


def write_fontconfig():
    """Chrome renderiza header/footer en un contexto aislado que ignora @font-face;
    ahí solo usa fuentes que fontconfig pueda localizar. Generamos un fontconfig
    propio que incluye el del sistema y añade FONTS_DIR, y lo pasamos a Chrome vía
    FONTCONFIG_FILE para que 'Space Grotesk' se resuelva por nombre sin instalarla.
    Solo aplica en Linux; en Windows Chrome usa DirectWrite y no hay fontconfig."""
    if IS_WINDOWS:
        return None
    conf = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>{FONTS_DIR.resolve()}</dir>
</fontconfig>
"""
    fd, path = tempfile.mkstemp(suffix=".conf", prefix="mdpdf-fc-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(conf)
    return path


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
.toc-page .toc a { text-decoration: none; color: #1a1a1a; }
.toc-page .toc a:hover { text-decoration: underline; }

/* ── Contenido ── */
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
}
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12pt; }
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
"""

DEBUG_PORT = 9333


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
    meta = {"title": "", "subject": "", "author": "", "master": "", "curso": ""}
    keys = {
        "**Asignatura:**": "subject",
        "**Autor:**": "author",
        "**Máster": "master",
        "**Curso:**": "curso",
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


def cover_html(meta, logo_uri):
    """Portada standalone — se renderiza sin header/footer."""
    logo_tag = f'<img class="logo" src="{logo_uri}" alt="Logo UJA">' if logo_uri else ""
    master_line = f'<p class="meta-line">{meta["master"]}</p>' if meta["master"] else ""
    curso_line  = f'<p class="meta-line">Curso {meta["curso"]}</p>' if meta["curso"] else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <style>@page {{ margin: 0; }}{font_face_css()}{CSS}</style>
</head>
<body>
<div class="cover">
  <div class="top">
    <h1>{meta["title"]}</h1>
    <p class="subtitle">{meta["subject"]}</p>
    {master_line}
    {curso_line}
    {logo_tag}
  </div>
  <p class="author">Realizado por {meta["author"]}</p>
</div>
</body>
</html>"""


def toc_content_html(meta, md_text):
    """Índice + contenido en un único HTML para que los links anchor funcionen."""
    parts = md_text.split("\n---\n", 1)
    body_md = parts[1] if len(parts) > 1 else md_text

    md = markdown.Markdown(
        extensions=[TocExtension(toc_depth="2-3"), "tables", "fenced_code", "codehilite"],
        extension_configs={"codehilite": {"noclasses": True, "guess_lang": False}},
    )
    content_body = md.convert(body_md)
    toc_tree = md.toc

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <style>@page {{ margin: 2cm; }}{font_face_css()}{CSS}</style>
</head>
<body>
<div class="toc-page">
  <h2>Índice de contenidos</h2>
  {toc_tree}
</div>
{content_body}
</body>
</html>"""


def merge_pdfs(*pdf_bytes_list):
    # append() (no add_page) preserva los enlaces internos y destinos con nombre,
    # así los links del índice siguen saltando a su sección tras fusionar.
    writer = pypdf.PdfWriter()
    for b in pdf_bytes_list:
        writer.append(io.BytesIO(b))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_header(meta):
    parts = " · ".join(filter(None, [meta["title"], meta["subject"]]))
    return (
        f'<div style="font-family:\'Space Grotesk\',Arial,sans-serif;font-weight:500;font-size:9.5pt;color:#666;'
        f'width:100%;padding-bottom:3px;'
        f'margin:0 0.8cm;box-sizing:border-box;text-align:center;">{parts}</div>'
    )


def make_footer(meta):
    return (
        f'<div style="font-family:\'Space Grotesk\',Arial,sans-serif;font-weight:500;font-size:9.5pt;color:#666;'
        f'width:100%;display:flex;align-items:center;margin:0 0.8cm;box-sizing:border-box;">'
        f'<span style="flex:1;"></span>'
        f'<span style="flex:1;text-align:center;">{meta["author"]}</span>'
        f'<span style="flex:1;text-align:right;">'
        f'<span class="pageNumber"></span> / <span class="totalPages"></span>'
        f'</span>'
        f'</div>'
    )


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

fc_path = write_fontconfig()
chrome_env = {**os.environ}
if fc_path:
    chrome_env["FONTCONFIG_FILE"] = fc_path

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
    env=chrome_env,
)

if not wait_for_chrome():
    print("Chrome no arrancó a tiempo")
    chrome.terminate()
    sys.exit(1)

try:
    targets = json.loads(
        urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json").read()
    )
    page_target = next(t for t in targets if t["type"] == "page")
    ws, send, wait_event = cdp_session(page_target["webSocketDebuggerUrl"])

    for md_path in md_files:
        pdf_path = md_path.with_suffix(".pdf")
        print(f"  {md_path.name} → {pdf_path.name}", end=" ", flush=True)

        md_text = md_path.read_text(encoding="utf-8")
        meta = extract_meta(md_text)
        logo_uri = find_logo(md_path)

        def render(html, *, display_hf=False, margin_top=0.8, margin_bottom=0.8, margin_lr=0.8):
            with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as f:
                f.write(html)
                tmp = f.name
            try:
                send("Page.enable", {})
                send("Page.navigate", {"url": Path(tmp).resolve().as_uri()})
                wait_event("Page.loadEventFired", timeout=10)
                time.sleep(0.3)
                result = send("Page.printToPDF", {
                    "printBackground": True,
                    "displayHeaderFooter": display_hf,
                    "headerTemplate": make_header(meta),
                    "footerTemplate": make_footer(meta),
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

        cover_bytes   = render(cover_html(meta, logo_uri),
                               margin_top=0, margin_bottom=0, margin_lr=0)
        content_bytes = render(toc_content_html(meta, md_text),
                               display_hf=True, margin_top=1.2, margin_bottom=1.0)

        pdf_bytes = merge_pdfs(cover_bytes, content_bytes)
        pdf_path.write_bytes(pdf_bytes)
        print(f"[OK, {len(pdf_bytes) // 1024} KB]")

    ws.close()
finally:
    chrome.terminate()
    chrome.wait()
    if fc_path and os.path.exists(fc_path):
        os.unlink(fc_path)
