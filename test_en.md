---
title: Locale Test Document
subtitle: English rendering check
comment: June 2026
author: Test User
logo: foto1.jpg
locale: en
---

## 1. Introduction

This short document verifies the **English locale** and a few features at once:
asset labels should read "Figure", "Table" and "Code block", and the automatic
index titles should be in English. It also uses an arbitrary cover image via the
`logo:` field instead of an auto-detected logo file.

<!-- caption: A snowy mountain at dawn -->
![Snowy mountain at dawn](foto1.jpg)

<!-- caption: Sample configuration values -->
| Name     | Type     | Default          |
|----------|----------|------------------|
| `margin` | `float`  | `1.15`           |
| `font`   | `string` | `Source Serif 4` |
| `size`   | `int`    | `14`             |

### 1.1 Code block kept with its text

The `<!-- keep -->` marker forces the block below to stay on the same page as
this paragraph:

<!-- keep -->
<!-- caption: Minimal greeting function -->
```python
def greet(name):
    return f"Hello, {name}!"
```

## 2. Second section

Figure and table counters reset on each section, so the first figure here is
labelled **Figure 2.1**.

<!-- caption: An aerial view of a forest -->
![Aerial view of a forest](foto2.jpg)
