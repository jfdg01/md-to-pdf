---
title: Theme Config Test
subtitle: Most settings loaded from sample.theme
theme: sample.theme
code_theme: monokai
---

## Theme file

This document sets only `theme: sample.theme`, plus a `code_theme: monokai`
override. Everything else — `locale`, `author`, `page_size`, `margins`,
`toc_depth`, and the font sizes (including a larger `caption_size`) — comes from
`sample.theme`, which also uses inline `# comments` after some values.

Precedence is `DEFAULT_META < .theme < front matter`, so `code_theme: monokai`
here wins over the theme's `nord`, while `author: Theme Default Author` comes
straight from the theme (this `.md` sets no author).

<!-- caption: Highlighted with the front-matter override (monokai) -->
```python
def main():
    print("theme override works")
```

### Larger headings and body

The `text_size`, `title_size`, `h2_size`, and `table_size` from the theme apply
throughout, with no per-document tuning.

<!-- caption: Table rendered at the theme's table_size -->
| Source        | Setting      | Where it came from |
|---------------|--------------|--------------------|
| `.theme`      | `code_theme` | overridden here    |
| front matter  | `code_theme` | wins (monokai)     |
