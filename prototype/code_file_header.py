"""PROTOTYPE, throw away. Five looks for a file-name header on code blocks.

Question: what should `<!-- file: path -->` above a fence look like in the PDF?
Run:  .venv/bin/python prototype/code_file_header.py
      .venv/bin/python prototype/code_file_header.py A A2 A3 A4 B B2 B3 B4
Out:  prototype/out/variant-<key>.pdf and prototype/out/compare[-<keys>].pdf
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

def _mix(color, other, t):
    """Blend two #rrggbb colors: t=0 gives `color`, t=1 gives `other`."""
    c = color.lstrip("#")
    o = other.lstrip("#")
    if len(c) != 6:
        return color
    rgb = [round(int(c[i:i + 2], 16) * (1 - t) + int(o[i:i + 2], 16) * t)
           for i in (0, 2, 4)]
    return "#" + "".join(f"{v:02x}" for v in rgb)


def _split(p):
    """`src/pkg/` dimmed, `main.py` bold."""
    d, _, f = p.rpartition("/")
    return (f'<span class="dir">{d}/</span>' if d else "") + f'<b>{f}</b>'


# Variations of A (tab) and B (bar). The originals A and B stay for reference.
VARIANTS.update({
    "A2": ("Tab, lighter shade + accent line", "before", f"""
.fh {{ display: inline-block; font-family: {MONO}; font-size: 0.8rem;
       padding: 4px 12px 3px; border-radius: 6px 6px 0 0;
       border-top: 2px solid #5a8fc4; }}
.fh + .codehilite, .fh + pre {{ border-top-left-radius: 0; }}
""", lambda p, bg, fg: f'<div class="fh" style="background:{_mix(bg, "#ffffff", 0.1)};color:{fg}">{p}</div>'),

    "A3": ("Tab, sans font, folder dimmed", "before", f"""
.fh {{ display: inline-block; font-family: {SANS}; font-size: 0.82rem;
       padding: 5px 14px; border-radius: 6px 6px 0 0; }}
.fh .dir {{ opacity: 0.5; }}
.fh + .codehilite, .fh + pre {{ border-top-left-radius: 0; }}
""", lambda p, bg, fg: f'<div class="fh" style="background:{bg};color:{fg}">{_split(p)}</div>'),

    "A4": ("Tab on a tab strip (editor window)", "before", f"""
.fs {{ border-radius: 4px 4px 0 0; padding: 4px 0 0 6px; font-size: 0; }}
.fh {{ display: inline-block; font-family: {MONO}; font-size: 0.78rem;
       padding: 4px 12px; border-radius: 5px 5px 0 0; }}
.fs + .codehilite, .fs + pre {{ border-radius: 0 0 4px 4px; }}
""", lambda p, bg, fg: (f'<div class="fs" style="background:{_mix(bg, "#000000", 0.35)}">'
                        f'<span class="fh" style="background:{bg};color:{fg}">{p}</span></div>')),

    "B2": ("Bar in the theme's color, slightly lighter", "before", f"""
.fh {{ font-family: {MONO}; font-size: 0.8rem; padding: 5px 12px;
       border-radius: 4px 4px 0 0; }}
.fh + .codehilite, .fh + pre {{ border-radius: 0 0 4px 4px; }}
""", lambda p, bg, fg: (f'<div class="fh" style="background:{_mix(bg, "#ffffff", 0.08)};color:{fg};'
                        f'border-bottom:1px solid {_mix(bg, "#ffffff", 0.18)}">{p}</div>')),

    "B3": ("Window bar with three dots", "before", f"""
.fh {{ font-family: {SANS}; font-size: 0.8rem; padding: 5px 12px;
       border-radius: 6px 6px 0 0; text-align: center; position: relative; }}
.fh .dots {{ position: absolute; left: 12px; top: 50%; margin-top: -4px; font-size: 0; line-height: 0; }}
.fh .dots i {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
               margin-right: 5px; }}
.fh + .codehilite, .fh + pre {{ border-radius: 0 0 6px 6px; }}
""", lambda p, bg, fg: (f'<div class="fh" style="background:{_mix(bg, "#ffffff", 0.08)};color:{fg}">'
                        '<span class="dots"><i style="background:#ff5f57"></i>'
                        '<i style="background:#febc2e"></i><i style="background:#28c840"></i></span>'
                        f'{p}</div>')),

    "B4": ("Light bar, folder dimmed, file bold, outlined", "before", f"""
.fh {{ font-family: {MONO}; font-size: 0.8rem; padding: 5px 12px;
       background: #f0f0f0; color: #222; border: 1px solid #d0d0d0;
       border-bottom: none; border-radius: 4px 4px 0 0; }}
.fh .dir {{ color: #888; }}
.fh + .codehilite, .fh + pre {{ border-radius: 0 0 4px 4px; }}
""", lambda p, bg, fg: f'<div class="fh">{_split(p)}</div>'),
})

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
    keys = sys.argv[1:] or list(VARIANTS)   # e.g. `A A2 A3 B B2` for a subset
    for key in keys:
        md_to_pdf.content_html = patched(key, original)
        pdf = out / f"variant-{key}.pdf"
        md_to_pdf.convert_one(HERE / "code_file_header.md", pdf)
        reader = PdfReader(pdf)
        compare.add_page(reader.pages[-1])   # the sample section page
        print(f"  {key} {VARIANTS[key][0]:32} -> {pdf.relative_to(HERE.parent)}")
    name = "compare.pdf" if not sys.argv[1:] else f"compare-{'-'.join(keys)}.pdf"
    compare.write(out / name)
    print(f"  compare (one page per variant) -> {(out / name).relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
