"""PROTOTYPE, throw away. Five looks for a file-name header on code blocks.

Question: what should `<!-- file: path -->` above a fence look like in the PDF?
Run:  .venv/bin/python prototype/code_file_header.py
Out:  prototype/out/variant-{A..E}.pdf and prototype/out/compare.pdf
      (compare.pdf = the sample page of each variant, one per page: flip pages
      to switch variants).
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
import md_to_pdf  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

MONO = "'Space Mono', 'DejaVu Sans Mono', monospace"
SANS = "'Space Grotesk', Arial, sans-serif"

# Each variant: (name, css, header_html(path, bg, fg) -> html placed by `where`)
# where = "before" (above the code box) or "inside" (first child of the box).
VARIANTS = {
    "A": ("Editor tab", "before", f"""
.fh {{ display: inline-block; font-family: {MONO}; font-size: 0.8rem;
       padding: 4px 12px; border-radius: 6px 6px 0 0; }}
.fh + .codehilite, .fh + pre {{ border-top-left-radius: 0; }}
""", lambda p, bg, fg: f'<div class="fh" style="background:{bg};color:{fg}">{p}</div>'),

    "B": ("Full-width title bar", "before", f"""
.fh {{ font-family: {MONO}; font-size: 0.8rem; padding: 5px 12px;
       background: #e2e2e2; color: #333; border-radius: 4px 4px 0 0;
       border-bottom: 1px solid #c8c8c8; }}
.fh + .codehilite, .fh + pre {{ border-radius: 0 0 4px 4px; }}
""", lambda p, bg, fg: f'<div class="fh">{p}</div>'),

    "C": ("Comment line inside the box", "inside", f"""
.fh {{ font-family: {MONO}; font-size: 0.8rem; opacity: 0.6;
       padding-bottom: 6px; margin-bottom: 8px;
       border-bottom: 1px dashed currentColor; }}
""", lambda p, bg, fg: f'<div class="fh" style="color:{fg}">{p}</div>'),

    "D": ("Corner badge", "inside", f"""
.code-block .codehilite, .code-block > pre {{ position: relative; }}
.fh {{ position: absolute; top: 0; right: 0; font-family: {SANS};
       font-size: 0.72rem; padding: 2px 8px; border-radius: 0 4px 0 4px;
       background: rgba(127,127,127,0.25); }}
""", lambda p, bg, fg: f'<div class="fh" style="color:{fg}">{p}</div>'),

    "E": ("Plain label above, no box", "before", f"""
.fh {{ font-family: {SANS}; font-weight: bold; font-size: 0.85rem;
       color: #333; margin: 0 0 4px 2px; }}
.fh::before {{ content: "File: "; font-weight: normal; color: #777; }}
.fh span {{ font-family: {MONO}; font-weight: normal; }}
""", lambda p, bg, fg: f'<div class="fh"><span>{p}</span></div>'),
}

# `<!-- file: X -->`, then the code-block wrapper, then the box (.codehilite
# div with the theme's inline style, or a bare <pre>).
BLOCK_RE = re.compile(
    r'<!--\s*file:\s*(?P<path>.*?)\s*-->\s*'
    r'(?P<wrap><div class="code-block[^"]*" id="[^"]*">)'
    r'(?P<open><div class="codehilite"[^>]*>|<pre\b[^>]*>)',
    re.DOTALL)


def _colors(open_tag):
    bg = re.search(r'background:\s*([^;"]+)', open_tag)
    fg = re.search(r'color:\s*([^;"]+)', open_tag[open_tag.find("<pre"):] if "<pre" in open_tag else "")
    return (bg.group(1).strip() if bg else "#f4f4f4"), (fg.group(1).strip() if fg else "#1a1a1a")


def patched(key, original):
    name, where, css, header = VARIANTS[key]

    def content_html(*a, **kw):
        html = original(*a, **kw)

        def sub(m):
            path = md_to_pdf.escape(m.group("path"))
            open_tag = m.group("open")
            # The fg color sits on the inner <pre style=...> right after the div.
            tail = html[m.end():m.end() + 300]
            fg_m = re.search(r'<pre[^>]*style="[^"]*color:\s*([^;"]+)', tail)
            bg, _ = _colors(open_tag)
            fg = fg_m.group(1).strip() if fg_m else "#1a1a1a"
            h = header(path, bg, fg)
            if where == "before":
                return m.group("wrap") + h + open_tag
            return m.group("wrap") + open_tag + h

        html = BLOCK_RE.sub(sub, html)
        html = html.replace("PROTOTYPE_VARIANT_NAME",
                            f"<p><b>Variant {key}: {name}</b></p>")
        return html.replace("</style>", css + "</style>", 1)
    return content_html


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    original = md_to_pdf.content_html
    compare = PdfWriter()
    for key in VARIANTS:
        md_to_pdf.content_html = patched(key, original)
        pdf = out / f"variant-{key}.pdf"
        md_to_pdf.convert_one(HERE / "code_file_header.md", pdf)
        reader = PdfReader(pdf)
        compare.add_page(reader.pages[-1])   # the sample section page
        print(f"  {key} {VARIANTS[key][0]:32} -> {pdf.relative_to(HERE.parent)}")
    compare.write(out / "compare.pdf")
    print(f"  compare (one page per variant) -> {(out / 'compare.pdf').relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
