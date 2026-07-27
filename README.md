# md-to-pdf

Turn Markdown into a polished PDF with a **cover page**, a **navigable table of
contents**, **lists of figures/tables/code blocks**, and a **running
header/footer** on every page. Good for reports, manuals, notes, or any
structured document.

Rendering is done by **WeasyPrint** (pure Python, no browser): fast, light, and
identical on every machine. The fonts (Source Serif 4, Space Grotesk, Space
Mono) ship with the repo in `assets/fonts/`.

---

## Requirements

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** to manage the environment and
  dependencies:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
  # Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- WeasyPrint's system libraries (Pango/Cairo). On Ubuntu/Debian:
  ```bash
  sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0
  ```
  On Windows, install them via WeasyPrint's docs (GTK runtime).

Python dependencies (`markdown`, `weasyprint`, `pypdf`, `watchdog`, `pygments`,
`pybtex`) are declared in `pyproject.toml` and pinned in `uv.lock`. `uv sync`
installs them into a project-local virtual environment (`.venv/`).

---

## Installation

The installer runs `uv sync` and registers the global `md-to-pdf` command.

**Linux / macOS**
```bash
cd /path/to/md-to-pdf
bash install.sh        # links md-to-pdf into ~/.local/bin
```
Make sure `~/.local/bin` is on your `PATH` (add to `~/.bashrc` if needed):
```bash
export PATH="$HOME/.local/bin:$PATH"
```

**Windows**
```powershell
cd C:\path\to\md-to-pdf
.\install.ps1          # add the repo folder to your user PATH, then open a new terminal
```

> The `.venv/` is per-machine and git-ignored. Run the installer once per
> machine after cloning.

---

## Usage

```bash
md-to-pdf report.md              # -> report.pdf next to the source
md-to-pdf a.md b.md              # several files
md-to-pdf notes/                 # every .md in a directory (no recursion)
md-to-pdf report.md -o final.pdf # choose the output name/path
md-to-pdf --watch report.md      # rebuild on every save (Ctrl-C to stop)
```

Each PDF is written next to its `.md` with the same name, unless `-o`/`--output`
is given. `-o` only applies to a single `.md`; with several files or a
directory it is ignored with a warning. `--watch` does an initial build, then
rebuilds on save (with a small debounce); it also watches directories for new
`.md` files.

---

## Document structure

A document starts with a **front matter** block (`key: value` pairs between
`---` lines), followed by the **body**:

```markdown
---
title: Document title
subtitle: An optional subtitle
author: Your Name
logo: images/cover.png
---

## Introduction

First section...

### A subsection

More text...
```

Sections are numbered automatically, so **don't write the number** in headings.
If `title` is omitted, the first `# ` heading in the body is used.

### Front matter keys

| Key              | Purpose                                                        | Shows in            |
|------------------|----------------------------------------------------------------|---------------------|
| `title`          | Document title (the only required key)                         | Cover + header      |
| `subtitle`       | Italic subtitle                                                | Cover + header      |
| `comment`        | Free extra line (date, course, note…)                          | Cover               |
| `author`         | Author                                                         | Cover + footer      |
| `logo`           | Path to **any** image for the cover (`none` disables it)       | Cover               |
| `locale`         | `es` (default) or `en`: language of "Figure"/"Table", indexes  | Whole document      |
| `code_theme`     | Syntax-highlight palette (see below)                           | Code blocks         |
| `numbering`      | Auto-number sections (default `true`; `false` to disable)      | Sections + TOC      |
| `toc_depth`      | Deepest TOC level: `3` (`###`), `4` (`####`, default), `5`     | TOC + bookmarks     |
| `page_size`      | `a4` (default), `a5`, `a3`, `letter`, `legal`, `b5`, `ledger`… | Whole document      |
| `orientation`    | `portrait` (default) or `landscape`                           | Whole document      |
| `margins`        | Body margins as CSS (`1.15in 0.85in 0.95in 0.85in`)           | Whole document      |
| `bibliography`   | Path to a `.bib` (BibTeX) file for citations                  | "References" section|
| `citation_style` | `numeric` (default, `[1]`) or `author-year` (`(Smith, 2020)`) | Citation markers    |
| `*_size`         | Per-section font sizes (see Font sizes)                        | The matching part   |
| `theme`          | Path to a `.theme` file of shared defaults (see Theme files)   | Whole document      |

Spanish aliases are accepted (`titulo`, `autor`, `imagen`, `idioma`,
`numeracion`, `tamaño`, `orientacion`, `margenes`, `bibliografia`,
`estilo_cita`…). Margins can also be set per side with `margin_top`,
`margin_right`, `margin_bottom`, `margin_left`.

### Body rules

- **`## ` = section**, and starts on a **new page**.
- **`### `/`#### `/`##### ` = subsections**, no page break.
- Sections are numbered automatically (`1.`, `1.1`, `1.1.1`…). Disable with
  `numbering: false` if your text already carries the numbers.
- The **TOC** lists headings up to `toc_depth` (default `####`) with clickable
  links; the PDF gets matching **bookmarks**.
- Standard Markdown works: **bold**, *italic*, lists, tables, `inline code`,
  fenced code blocks, blockquotes, links, horizontal rules.

### Per-heading TOC control

Put a comment on the line above a heading to override `toc_depth` for it:

```markdown
<!-- toc -->
##### Force this deep heading into the TOC

<!-- no-toc -->
### Keep this one out of the TOC
```

Both marks affect the TOC and the PDF bookmarks alike.

### Figures, tables, and code blocks

These are numbered **Figure x.y**, **Table x.y**, **Code block x.y** (where *x*
is the section and *y* the counter within it, reset each section). Each type
gets its own list at the start of the document.

**Every figure, table, and code block must have a caption**, or the converter
refuses to build the PDF. Add it with an HTML comment on the line just above:

```markdown
<!-- caption: Overall system architecture -->
![Block diagram](blocks.png)
```

Images may instead use their alt text (`![alt](img)`) as the caption.

### Cross-references

Link to a figure/table/code block by its number with double brackets:
`[[fig-2-1]]`, `[[tab-2-1]]`, `[[code-2-1]]` (format: `type-section-index`). It
becomes a link whose visible text is the number ("Figure 2.1"). Unknown anchors
are left untouched and reported on the console.

### Keep with previous

Put `<!-- keep -->` on the line above an element to force it onto the same page
as the preceding content (instead of pushing it to the next page). If it
doesn't fit whole, it splits. Useful so a code block stays with its intro text.

```markdown
Like the following function:

<!-- keep -->
<!-- caption: Main entry point -->
` ``python
def main():
    ...
` ``
```

### Citations and bibliography

Point `bibliography:` at a **BibTeX** file (path relative to the `.md`, like
`logo:`) and cite in the body with `[@key]` (group several as `[@a; @b]`):

```markdown
---
title: My report
bibliography: refs.bib
citation_style: numeric   # numeric (default) | author-year
---

## Introduction

The method builds on prior work [@smith2020; @brown2018].
```

Each `[@key]` becomes a linked marker — `[1]` (numeric) or `(Smith, 2020)`
(author-year) — that jumps to its entry. A **References** section
("Referencias" with `locale: es`) is generated automatically with only the
cited entries; it is a normal numbered section and appears in the TOC and
bookmarks. Order is by appearance (numeric) or alphabetical by author
(author-year). Missing keys are reported and left visible.

An entry's **link is written out in full** and made clickable, so the
bibliography stays usable on paper. It is taken from `url`, from a `\url{...}`
inside `howpublished`, or from `doi` (resolved via doi.org). Add `urldate` (or
`accessed`) and it is printed alongside as "accedido el …" / "accessed …",
verbatim — write the date in the `.bib` in whatever form the document should
show:

```bibtex
@misc{nvidia2024orinpower,
  title        = {Platform Power and Performance},
  author       = {{NVIDIA}},
  howpublished = {\url{https://docs.nvidia.com/jetson/...}},
  year         = {2024},
  urldate      = {27 de julio de 2026}
}
```

### Page size and margins

Defaults to **A4 portrait**. Override with `page_size`, `orientation`, and
`margins`:

```markdown
---
title: Landscape notes
page_size: letter
orientation: landscape
margins: 1in 1.25in
---
```

These apply to cover, indexes, and body alike. Unknown values are reported and
fall back to the default.

### Theme files

To share a set of defaults across many documents, put them in a `.theme` file
(same `key: value` format as the front matter) and point at it with `theme:`:

```markdown
---
title: My report
theme: house-style.theme   # path relative to the .md
---
```

Precedence is **built-in defaults < `.theme` < the document's front matter**, so
any key the document sets itself overrides the theme. A `.theme` can hold any
front-matter key (page size, margins, `code_theme`, citation style, font sizes,
even `author`), but not `theme` itself (themes don't chain). A `#` starts a
comment — either a whole line or inline after a value (`text_size: 14  # body`);
a `#` with no space before it (like a `#rrggbb` color) is kept as part of the
value. The optional `---` delimiters are allowed, so a front matter can be
reused as a theme.

Copy [`template.theme`](template.theme) to get started: it lists every key set
to its built-in default, so it renders identically to no theme until you change
a value.

### Syntax highlighting

Controlled at two levels.

**1. Whole document — `code_theme` in the front matter.** Accepts:

- *(empty)* or `custom` → the bundled **muted dark palette** (slate-grey
  background, desaturated accents) defined in `src/md_to_pdf.py`. Default.
- Any **Pygments theme**: `monokai`, `dracula`, `github-dark`,
  `solarized-light`, `nord`, `gruvbox-dark`, `friendly`… (full list:
  `python -m pygments -L styles`).

**2. Per block — `<!-- code-theme: NAME -->`** on the line just above a fence,
so one block can use a different palette from the document. If a `<!-- caption:
-->` is also present, put it **above** the `<!-- code-theme: -->`.

```markdown
<!-- caption: Config (dark theme) -->
<!-- code-theme: monokai -->
` ``json
{ "printBackground": true }
` ``
```

To customize the default palette, edit the `CODE_PALETTE` dict near the top of
`src/md_to_pdf.py` (each key is a hex color).

### Font sizes

Every piece of rendered text has a size key, settable in the front matter or a
theme. A bare number is points (`14` → `14pt`); any CSS unit (`1.2em`, `12px`)
is kept as-is.

| Key                  | Sizes                                              | Default  |
|----------------------|----------------------------------------------------|----------|
| `text_size`          | Body text                                          | `11pt`   |
| `title_size`         | Cover title                                        | `26pt`   |
| `subtitle_size`      | Cover subtitle                                     | `15pt`   |
| `comment_size`       | Cover comment line                                 | `11.5pt` |
| `author_size`        | Cover author line (footer uses `footer_size`)      | `13pt`   |
| `h1_size`…`h6_size`  | Body headings, per level                           | varies   |
| `code_size`          | Code blocks and inline code                        | `10pt`   |
| `table_size`         | Tables                                             | `10.5pt` |
| `caption_size`       | Figure captions, table captions, code-block labels | `9.5pt`  |
| `index_heading_size` | "Contents" / "List of …" page headings             | `17pt`   |
| `header_size`        | Running header                                     | `9pt`    |
| `footer_size`        | Running footer and page number                     | `9pt`    |

The **table-of-contents** lines have their own sizes, per nesting level:
`toc_size` sets every level at once, while `toc1_size`…`toc4_size` override an
individual level (`1` = top-level `##` entries, `2` = `###`, `3` = `####`,
`4` = `#####`; deeper levels inherit level 4). A per-level key wins over the
general `toc_size`. Defaults are `11pt`/`10.5pt`/`10pt`/`10pt`. The general
`toc_size` also sizes the **lists of figures/tables/code blocks** (default
`10.5pt`).

---

## Notes

- Header, footer, cover, and body use the embedded fonts in `assets/fonts/`, so
  output is identical anywhere with nothing to install. Long titles are clipped
  in the header so they stay within the margin.
- The PDF carries document metadata (title, author, subtitle).
- When converting several files, a failure is reported with `[ERROR: …]` and the
  rest continue; the command exits non-zero if anything failed.
