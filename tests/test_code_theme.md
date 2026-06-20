---
title: Code Theme
subtitle: Document-wide Pygments theme, manual numbering
author: Test User
locale: en
code_theme: monokai
numbering: false
---

## 1. Document-wide theme

With `code_theme: monokai`, every code block uses that Pygments palette unless a
block overrides it with `<!-- code-theme: -->`. Try other names like `dracula`,
`nord`, or `solarized-light`.

With `numbering: false`, sections are **not** auto-numbered, so the numbers here
(`1.`, `2.`…) are written by hand.

<!-- caption: Python under the monokai theme -->
```python
def quicksort(xs):
    if len(xs) <= 1:
        return xs
    pivot = xs[len(xs) // 2]
    lo = [x for x in xs if x < pivot]
    hi = [x for x in xs if x > pivot]
    return quicksort(lo) + [pivot] + quicksort(hi)
```

## 2. Per-block override

<!-- caption: This block overrides the document theme -->
<!-- code-theme: solarized-light -->
```bash
uv sync
md-to-pdf report.md
```
