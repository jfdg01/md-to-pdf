# Figure images in md-to-pdf reports

How to prepare a PNG or JPEG for a figure, and how to capture a window so that every capture in every report has the same edges. Charts are SVG and have their own guide: `docs/charts.md`.

## 1. The image has no margin of its own

`md-to-pdf` draws every figure image inside a thin dashed frame with a 4 px gap (`figure img` in `src/md_to_pdf.py`). The frame and the gap are the only margin a figure needs.

- **The PNG holds content up to its last pixel.** The first and last row and column belong to the thing you show. A margin of 0 px is the target. A few pixels of the application's own edge is acceptable.
- **A margin inside the PNG shows twice.** It adds to the 4 px gap, so the dashed frame floats far from the content. Two captures of the same kind, one with a margin and one without, then look different on the same page.
- **A margin colour depends on the tool that wrote the file.** The same shadow area becomes a black band in one converter and a transparent band in another. Black clashes with the frame; transparent leaves a hole. Do not rely on either. Remove the margin.
- **Crop, do not edit.** Cutting a margin off keeps every remaining pixel as captured. Do not redraw, blur or recolour.
- **A region or a page capture follows the same rule.** Crop away the empty desktop, the blank page margin and the browser chrome you did not mean to show.

## 2. Capture a window the same way every time

A window capture must hold the window and nothing else. A modern desktop draws a shadow area around the window, and a plain capture of the window id includes it. Use the steps for your system. The steps for X11 were tested.

### Linux, X11 (GTK windows such as `gnome-terminal`, Firefox, Wireshark)

The window states the width of its shadow in the property `_GTK_FRAME_EXTENTS`: left, right, top, bottom. Capture the whole window, then crop exactly that amount.

```bash
W=<window id>                      # xdotool search, or xdotool getactivewindow
read l r t b < <(xprop -id $W _GTK_FRAME_EXTENTS | sed 's/.*= //; s/,//g')
xwd -id $W -silent | ffmpeg -y -f xwd_pipe -i - raw.png
ffmpeg -y -i raw.png -vf "crop=iw-$l-$r:ih-$t-$b:$l:$t" out.png
```

- Take the id of the window you mean. `xdotool search --class` lists helper windows too, and some have a 10x10 size. Pick the one whose `_GTK_FRAME_EXTENTS` is set and whose size fits.
- A maximised or tiled window has extents `0, 0, 0, 0`. The crop then changes nothing, which is right.
- `xwd` copies what is on the screen. Another window above the target shows in the capture. Raise the target and look at the result before you use it.
- Write the file through a path that keeps the alpha channel, as above. The rounded corners of the window then stay transparent, not black.

### Other systems

- **macOS:** `screencapture -o -l <window id> out.png`. The `-o` flag leaves the shadow out.
- **Windows:** `Alt` + `PrtSc` captures the active window without the shadow.
- **Wayland:** use the screenshot tool of the desktop in window mode, and then run the edge check below. If a band remains, crop it by its measured size.

### Make the capture repeatable

- Use one window size for one kind of capture. Fix the size with the program's own option (for a terminal, its `--geometry` in columns and rows), not by eye. Every capture then has the same width and the same scale on the page.
- Use one theme, one font and one font size for all captures of the same kind. Do not change them between captures.
- Keep titles, tab bars and prompts free of names that a reader should not see: script names, test profile names, temporary paths.
- Say in the report how you captured. One sentence is enough.

## 3. Check the edges before you embed

Look at the PNG at 100 %. The edge must be the window border, not a band of black or of empty space. A check by program:

```bash
uv run --with pillow python3 -I - out.png <<'E'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGBA"); w, h = im.size; px = im.load()
for side, line in (("left", [px[x, h // 2] for x in range(w)]), ("top", [px[w // 2, y] for y in range(h)])):
    band = next((i for i, p in enumerate(line) if p[3] == 255 and p[:3] != (0, 0, 0)), len(line))
    print(side, "band of", band, "px that is black or transparent")
E
```

A band of 0 px passes. A band of 5 px or more is a margin. Crop it.

Build the PDF and look at the page: the frame must sit close to the content on every side.

## 4. Checklist before you commit a figure

- [ ] The first and last pixel row and column are content, not black and not transparent.
- [ ] A window capture was cropped by its frame extents, or taken with a no-shadow option.
- [ ] Captures of the same kind have the same width, theme and font.
- [ ] No private data in the image: other windows, tabs, user names that must stay hidden.
- [ ] You looked at the PDF page.
