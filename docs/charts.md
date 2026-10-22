# Charts in md-to-pdf reports

How to make a chart for a report, and the rules that keep every chart in every report looking the same.
`docs/charts/example.py` is a working generator with three sample charts. This file explains it.

A chart is a plain **SVG image**. `md-to-pdf` needs no special support: it embeds the file like any other
image, and the Markdown alt text becomes the numbered caption.

```markdown
![Memory over time for two configurations](img/line-limit.svg)
```

## 1. Workflow

1. **Measure first.** Keep the numbers in a small table (a Python dict, a CSV). If a number varies from run to run,
   run it at least twice and plot every run. One run is an anecdote; two runs show the spread.
2. **Copy the generator.** Copy `docs/charts/example.py` next to the report. The sample data is plain Python at the top
   of each `fig_*` function (`SERIES_A`, `RUNS`, `CPU`, `MEM`). Replace it. The generator never reads raw logs;
   clean the data before it gets there (for example, remove repeated samples from a stream).
3. **Generate the SVG files.** `python3 -I example.py` writes `img/*.svg`. The script uses only the Python standard library.
4. **Look at every SVG.** Open it in a browser or screenshot it. A colour check cannot find layout problems. Look for
   text that overlaps a mark, text that leaves the canvas, and a label that crosses a limit line.
5. **Embed the SVG and build the PDF.** Then look at the PDF page. The page scales the SVG to about 84 % of its pixel
   size, so check that the text is still readable.
6. **Say how the data was made.** The report states how many runs, on which machine, and what could bias the result.

Why hand-written SVG and not a plotting library: the mark rules in section 3 (a 4 px rounded data end with a square
base, a 2 px ring around a dot) are exact in SVG and awkward in most plotting libraries. The generator is about 200 lines
and has no dependency.

## 2. Pitfalls

- **The font comes from the system.** The SVG text asks for `Space Grotesk`. WeasyPrint finds it through fontconfig, not
  through the `@font-face` rules of the report. On a machine without the font installed, the text falls back to a
  generic sans-serif and the widths change. Install the font before you build.
- **In Space Grotesk the letter `O` looks like the digit `0`.** An acronym such as "OOM" reads as "00M". Write the
  word out.
- **The `T` text factor.** The canvas is about 720 px wide and the page scales it down. Every font size is multiplied by
  `T = 1.2` so the smallest text stays at 8 pt or more on paper. Change `T`, not each size.
- **A label that crosses a limit line or the grid.** Draw a rectangle in the surface colour behind the label (see
  `fig_paired_panels`). Do not move the label away from its bar.
- **Space for the right-hand labels.** An end label needs about 170 px after the last point. Widen the canvas; do not
  shrink the plot until the label is cropped.

## 3. Design rules

### Form

| The reader must… | Form |
|---|---|
| Compare a value between groups | Horizontal bars. Zero-based axis. |
| See change over time | Line, 2 px, with an end dot and an end label. |
| See the spread between repeated runs | Bars = mean, one dot per run in ink colour. Say it in the legend. |
| Compare a value with a limit | A solid line in secondary ink across the plot, with a label. Never a dashed line. |
| Compare two measures with different units | Two panels side by side, each with its own axis. **Never** a dual axis. |

### Colour

| Slot | Name | Hex | Use |
|---|---|---|---|
| 1 | blue | `#2a78d6` | first series |
| 2 | orange | `#eb6834` | second series |
| 3 | aqua | `#1baf7a` | third series |

- Use the slots in this order. Never cycle. **Three series is the limit** for bars and side-by-side panels. Fold the
  rest into "Other" or draw a second chart.
- Colour follows the entity, not its rank. The same thing has the same colour in every chart of a report.
- The three colours were checked for separation under colour-vision deficiency and under normal vision. All pairs pass.
  One weakness remains: aqua has a contrast of 2.74:1 against the surface, below the 3:1 target. The answer is a visible
  value on every aqua mark and a legend that names every series, so the colour never carries the meaning alone.
  Re-check the set if you change a colour.
- Text colours: primary ink `#0b0b0b`, secondary ink `#52514e`. **Text never uses a series colour.** A coloured mark next
  to the text carries the identity.
- Surface `#fcfcfb` (the SVG is transparent; this colour is for dot rings and label backgrounds). Grid `#e1e0d9`,
  axis `#c3c2b7`.

### Marks

| Mark | Rule |
|---|---|
| Bar | At most 24 px thick (20 px, or 12 px when 3 bars share a row). Data end rounded to 4 px (3 px for 12 px bars). Base square. |
| Line | 2 px, round joins. |
| Dot | Radius 4 px, with a 2 px ring in the surface colour. |
| Grid | 1 px, solid, one step off the surface. |
| Gap between bars of one row | 2 px. |

### Labels

- Show a legend when there are 2 or more series. It sits above the plot on one row: colour mark, then text in ink.
- Put the value at the tip of each bar. A PDF has no hover, so the tip label replaces the tooltip.
- Put the series name at the end of a line (direct label). Do not nudge labels apart; use free space and keep a colour
  mark beside the label.
- Give each panel a title in 600 weight. When the direction of "good" is not obvious, add one line under the title
  ("higher is better" / "lower is better").
- Leave the chart title out of the SVG. The caption comes from the Markdown alt text.
- Format numbers in the language of the document (`DECIMAL` and `THOUSANDS` at the top of the generator).

## 4. Templates in `example.py`

| Function | Chart | Use it as a template for |
|---|---|---|
| `fig_line_limit` | Line chart over time with a limit line | A value over time and a hard limit |
| `fig_grouped_runs` | 3 panels of grouped bars, one dot per run | A comparison with repeated runs |
| `fig_paired_panels` | 2 panels of bars grouped 3 per row, limit lines | Peaks per component against a limit |

The helpers (`hbar`, `dot`, `legend`, `axis_ticks`, `text`, `num`) are the vocabulary. A new chart is a new `fig_*`
function that builds a list of SVG strings and passes it to `svg(width, height, body)`.

## 5. Checklist before you commit a chart

- [ ] The data in the file is the data you measured (two runs if it varies).
- [ ] 3 series at most, in slot order, with the same colour for the same entity in every chart.
- [ ] No dual axis. No dashed lines. No text in a series colour.
- [ ] Every bar has its value. Every limit has a label.
- [ ] Nothing overlaps or leaves the canvas. You looked at it.
- [ ] You looked at the PDF page and the text is readable.
- [ ] The report says how many runs, on which machine, and what could bias the result.
