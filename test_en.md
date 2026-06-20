---
title: Locale Test Document
subtitle: English rendering check
comment: June 2026
author: Test User
logo: assets/img/foto1.jpg
locale: en
bibliography: test_refs_en.bib
citation_style: author-year
---

## Introduction

This short document verifies the **English locale** and a few features at once:
asset labels should read "Figure", "Table" and "Code block", and the automatic
index titles should be in English. It also uses an arbitrary cover image via the
`logo:` field instead of an auto-detected logo file.

<!-- caption: A snowy mountain at dawn -->
![Snowy mountain at dawn](assets/img/foto1.jpg)

<!-- caption: Sample configuration values -->
| Name     | Type     | Default          |
|----------|----------|------------------|
| `margin` | `float`  | `1.15`           |
| `font`   | `string` | `Source Serif 4` |
| `size`   | `int`    | `14`             |

### Code block kept with its text

The `<!-- keep -->` marker forces the block below to stay on the same page as
this paragraph:

<!-- keep -->
<!-- caption: Minimal greeting function -->
```python
def greet(name):
    return f"Hello, {name}!"
```

## Second section

Figure and table counters reset on each section, so the first figure here is
labelled **Figure 2.1**.

Citations use `[@key]` and link to the auto-generated **References** section.
A single citation [@brown2018] and a grouped one [@smith2020; @brown2018] render
author-year markers, since this document sets `citation_style: author-year`.

<!-- caption: An aerial view of a forest -->
![Aerial view of a forest](assets/img/foto2.jpg)
