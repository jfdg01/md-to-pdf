"""Checks for the thesis features. Run: uv run python tests/test_thesis.py"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import md_to_pdf as m  # noqa: E402


def render(body, bib=None, **meta):
    """content_html for `body`, with the console warnings captured."""
    full = {**m.DEFAULT_META, "title": "T", **meta}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        html = m.content_html(full, body, m.get_strings(full["lang"]),
                              m.resolve_code_style(""),
                              "A4", bib)
    return html, err.getvalue()


def body_of(html):
    return html.split('<main class="body">', 1)[1]


def test_caption_top():
    md = ("## S\n\nSee [[fig-1-1]], [[tab-1-1]] and [[code-1-1]].\n\n"
          "![Cat](c.png)\n\n<!-- caption: Tab -->\n| a |\n|---|\n| 1 |\n\n"
          "<!-- caption: Code -->\n```python\nx = 1\n```\n")
    b = body_of(render(md, caption_position="top")[0])
    assert b.index("<figcaption>") < b.index("<img"), "figure caption on top"
    assert b.index('class="code-label"') < b.index('class="codehilite"')
    assert "caption-side: top" in render(md, caption_position="top")[0]
    below = body_of(render(md)[0])
    assert below.index("<figcaption>") > below.index("<img"), "default stays below"


def test_image_row():
    md = ("## S\n\n[[fig-1-1]]\n\n<!-- caption: Before and after -->\n"
          "![Before](a.png) ![After](b.png)\n")
    b = body_of(render(md, lang="en")[0])
    assert b.count("<figure") == 1, "one figure for the whole row"
    assert "(a) Before" in b and "(b) After" in b
    assert "Figure 1.1: Before and after" in b
    try:  # the alt texts are sub-captions: the row needs its own caption
        render("## S\n\n![A](a.png) ![B](b.png)\n")
        assert False, "a row without a caption must fail"
    except ValueError as e:
        assert "Figura 1.1" in str(e)


def test_footnotes():
    html, _ = render("## S\n\nText[^n] more.\n\n[^n]: A *note*.\n")
    b = body_of(html)
    assert 'Text<span class="fn">A <em>note</em>.</span> more.' in b, b
    assert 'class="footnote"' not in b, "no list of notes at the end"
    assert "float: footnote" in html


def test_math():
    md = ("## S\n\nInline $a_1 + b_1$ costs $5 and $6. See [[eq-1-1]].\n\n"
          "$$\n\\frac{a}{b}\n$$\n\n`$x$` stays.\n")
    b = body_of(render(md)[0])
    assert b.count('<span class="math">') == 2, "one inline + one block"
    assert "<em>" not in b, "math underscores are not emphasis"
    assert "costs $5 and $6." in b
    assert '<div class="math-block" id="eq-1-1">' in b
    assert '<span class="eq-num">(1.1)</span>' in b
    assert '<a href="#eq-1-1" class="xref">(1.1)</a>' in b
    assert "<code>$x$</code>" in b


def test_acronyms():
    md = ("*[HTML]: HyperText Markup Language\n\n## S\n\nUse HTML and HTML.\n")
    html, _ = render(md)
    assert body_of(html).count('<a class="abbr" href="#abbr-html">HTML</a>') == 2
    idx = html.split('<main class="body">')[0]
    assert "Lista de siglas" in idx
    assert '<dt id="abbr-html">HTML</dt><dd>HyperText Markup Language</dd>' in idx


def test_uncited_warning():
    md = ("## S\n\nSee [[fig-1-1]].\n\n![Cat](c.png)\n\n"
          "<!-- caption: Tab -->\n| a |\n|---|\n| 1 |\n\nAs [[tab-1-1]] shows.\n\n"
          "<!-- caption: Code -->\n```python\nx = 1\n```\n\n$$\nx\n$$\n")
    _, err = render(md, lang="en")
    assert "Figure 1.1" not in err, err
    assert "Table 1.1 appears before its first cross-reference" in err, err
    assert "Code block 1.1 is not cited" in err, err
    assert "Equation (1.1) is not cited" in err, err


BIB = r"""
@misc{spring,
  author = {{Spring}},
  title = {Cross Site Request Forgery (CSRF)},
  howpublished = {Spring Security Reference},
  url = {https://docs.spring.io/csrf.html},
  urldate = {14 oct. 2026},
}
@article{perez,
  author = {P{\'e}rez, Ana and L{\'o}pez, Blas},
  title = {Title of the article},
  journal = {Journal Name},
  volume = {3}, number = {2}, pages = {10--20}, year = {2024},
}
"""


def bib(tmp=Path("/tmp/md_to_pdf_test")):
    tmp.mkdir(exist_ok=True)
    (tmp / "refs.bib").write_text(BIB.replace(r"{\'e}", "é").replace(r"{\'o}", "ó"))
    return m.load_bibliography(tmp / "doc.md", {"bibliography": "refs.bib"})


def test_ieee_references():
    md = "## S\n\nAs [@spring] and [@perez; @spring] say, not [@nope].\n"
    html, err = render(md, bib(), lang="es")
    b = body_of(html)
    assert ('As [<a href="#ref-spring" class="cite">1</a>] and '
            '[<a href="#ref-perez" class="cite">2</a>], '
            '[<a href="#ref-spring" class="cite">1</a>] say') in b, b
    assert "@nope" in b and "'@nope' is not in the bibliography" in err
    assert "2. Referencias" in b, "a numbered section at the end"
    assert ('<span class="ref-num">[1]</span>Spring, “Cross Site Request Forgery '
            '(CSRF),” <em>Spring Security Reference</em>. Accedido: 14 oct. 2026. '
            '[En línea]. Disponible: <a class="ref-url" '
            'href="https://docs.spring.io/csrf.html">https://docs.spring.io/csrf.html'
            '</a>') in b, b
    assert ('<span class="ref-num">[2]</span>A. Pérez y B. López, “Title of the '
            'article,” <em>Journal Name</em>, vol. 3, n.º 2, pp. 10–20, 2024.') in b
    en = body_of(render(md, bib(), lang="en")[0])
    assert ("A. Pérez and B. López, “Title of the article,” <em>Journal Name</em>, "
            "vol. 3, no. 2, pp. 10–20, 2024.") in en
    assert "Accessed: 14 oct. 2026. [Online]. Available: " in en


def test_plain_pre_is_a_code_block():
    b = body_of(render("## S\n\n[[code-1-1]]\n\n<!-- caption: Raw -->\n<pre>x</pre>\n")[0])
    assert 'class="code-block" id="code-1-1"' in b and "img-row" not in b, b


def test_math_in_heading_and_caption():
    md = ("## Energy $x$\n\nSee [[fig-1-1]] and [[tab-1-1]].\n\n"
          "<!-- caption: Plot of $x^2$, from [@spring] -->\n![P](p.png)\n\n"
          "<!-- caption: a < b -->\n| a |\n|---|\n| 1 |\n")
    html, _ = render(md, bib())
    assert "MATHFORMULA" not in html, "no marker leaks into the TOC"
    assert ">1. Energy x</a>" in html.split('<main class="body">')[0]
    cap = body_of(html).split("<figcaption>", 1)[1].split("</figcaption>")[0]
    assert '<span class="math"><svg' in cap, cap
    assert '[<a href="#ref-spring" class="cite">1</a>]' in cap, cap
    assert "a &lt; b" in body_of(html), "plain caption text stays escaped"


def test_acronym_inside_a_link():
    html, _ = render("*[PDF]: Portable Document Format\n\n## S\n\n[the PDF spec](http://x)\n")
    assert '<a href="http://x">the PDF spec</a>' in body_of(html), body_of(html)
    assert '<dt id="abbr-pdf">PDF</dt>' in html


def test_footnote_cited_twice_and_with_a_list():
    html, err = render("## S\n\nA[^n] B[^m] C[^n].\n\n[^n]: One.\n[^m]: Two.\n\n    - item\n")
    b = body_of(html)
    assert b.count('<span class="fn">One.</span>') == 1, b
    assert 'C<sup class="fn-again">1</sup>.' in b, b
    assert "footnote 'm' keeps only its paragraphs" in err, err
    assert '<span class="fn">Two.</span>' in b, "no empty paragraph after the note"


def test_row_of_more_than_four_images():
    try:
        render("## S\n\n<!-- caption: Five -->\n" + " ".join(f"![{c}]({c}.png)" for c in "abcde"))
        assert False, "a row of 5 images must fail"
    except ValueError as e:
        assert "2 to 4" in str(e), e


def test_ieee_month():
    tmp = Path("/tmp/md_to_pdf_test")
    tmp.mkdir(exist_ok=True)
    (tmp / "m.bib").write_text("@article{a, author={Ana Pérez}, title={T}, journal={J},"
                               " month=oct, year={2024}}")
    entries = m.load_bibliography(tmp / "doc.md", {"bibliography": "m.bib"})
    assert "<em>J</em>, Oct. 2024." in body_of(render("## S\n\n[@a]\n", entries, lang="en")[0])
    assert "<em>J</em>, oct. 2024." in body_of(render("## S\n\n[@a]\n", entries)[0])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
