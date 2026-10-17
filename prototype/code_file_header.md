---
title: Prototype — code block file name
author: md-to-pdf
numbering: true
---

# Sample section

PROTOTYPE_VARIANT_NAME

The converter starts here. The function reads the file and writes the PDF:

<!-- caption: Main entry point -->
<!-- file: src/main.py -->
```python
def main():
    args = parse_args()
    for path in args.files:
        convert(path)
```

A config file with a dark theme on the block:

<!-- caption: Export settings -->
<!-- file: config/export.json -->
<!-- code-theme: monokai -->
```json
{ "printBackground": true, "pageSize": "A4" }
```

A long path, to check how the header wraps or cuts:

<!-- caption: Deep module -->
<!-- file: src/very/deep/package/structure/with/a/long/module_name_here.py -->
```python
VALUE = 42
```

A block with no file name, for comparison:

<!-- caption: Shell command -->
```bash
md-to-pdf informe.md
```
