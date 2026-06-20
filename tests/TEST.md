---
title: Feature Showcase
subtitle: A visual check of every general feature
comment: md-to-pdf test document
author: Test User
logo: ../assets/img/logo_uja.webp
locale: en
bibliography: test_refs.bib
theme: ../main.theme
---

## Headings and numbering

Sections (`##`) start on a new page and are auto-numbered (`1.`, `2.`…). This
document shows every general feature; document-wide options (locale, page size,
code theme, citation style) live in the other test files.

### Subsection

Auto-numbered `x.y`.

#### Sub-subsection

Auto-numbered `x.y.z`, and it reaches the default TOC depth.

##### Level-5 heading (not in the TOC by default)

<!-- toc -->
##### Forced into the TOC with `<!-- toc -->`

<!-- no-toc -->
### Hidden from the TOC with `<!-- no-toc -->`

## Text and links

**Bold**, *italic*, ***bold italic***, `inline code`, and an external
[link to python.org](https://www.python.org). Internal TOC and bookmark links
are generated automatically.

> A blockquote with **formatting**, `code`, and a second line that joins the
> same visual block.

A horizontal rule follows:

---

## Lists

- Unordered item
- Nested:
  - Child A
  - Child B
    - Grandchild
- Back to level one

1. Ordered step
2. Another step
   1. Sub-step 2.1
   2. Sub-step 2.2
3. Final step

## Code blocks

<!-- caption: Plain block, no language -->
```
$ md-to-pdf report.md
  report.md -> report.pdf [OK, 142 KB]
```

<!-- caption: Python with syntax highlighting -->
```python
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
```

A per-block theme overrides the document theme via `<!-- code-theme: -->`:

<!-- caption: JSON with a per-block monokai theme -->
<!-- code-theme: monokai -->
```json
{ "printBackground": true, "paperWidth": 8.27 }
```

The `<!-- keep -->` marker pins the block to the previous paragraph:

<!-- keep -->
<!-- caption: Greeting function kept with its intro -->
```python
def greet(name):
    return f"Hello, {name}!"
```

## Tables

<!-- caption: Basic table -->
| Name     | Type     | Default          |
|----------|----------|------------------|
| `margin` | `float`  | `1.15`           |
| `font`   | `string` | `Source Serif 4` |

<!-- caption: Column alignment -->
| Left        | Center      | Right     |
|:------------|:-----------:|----------:|
| text        | text        | 1,234.56  |
| longer text | longer text | 99.00     |

## Figures and cross-references

A caption via HTML comment:

<!-- caption: A snowy mountain at dawn -->
![Snowy mountain](../assets/img/foto1.jpg)

A caption taken from the image alt text:

![Aerial view of a forest](../assets/img/foto2.jpg)

Counters reset each section, so the figures above are **Figure 6.1** and
**Figure 6.2**. Reference them by number: see [[fig-6-1]] and [[fig-6-2]].

## Citations

Citations use `[@key]` and link to the auto-generated **References** section,
which lists only the cited entries. A single citation [@smith2020] and a grouped
one [@brown2018; @lee2021] render numeric markers by default.
