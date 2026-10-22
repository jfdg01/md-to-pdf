#!/usr/bin/env python3
"""Reference SVG chart generator for md-to-pdf reports (docs/charts.md explains it).

Writes three sample charts into img/: a line chart with a limit line, grouped horizontal bars with one dot
per run, and paired-panel bars with limit lines. Python stdlib only. Copy this file next to your report,
replace the sample data and the labels, run it, and embed the SVG files as images.
"""
from pathlib import Path

# --- Tokens (light mode) -----------------------------------------------------
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"  # categorical slots 1-3, always in this order
FONT = "Space Grotesk, sans-serif"
T = 1.2  # text factor: the page scales a figure to ~84 %, so text stays at 8 pt or more on paper
DECIMAL, THOUSANDS = ".", ","  # number format; use ",", " " for Spanish, for example
OUT = Path(__file__).parent / "img"


def num(v, dec=0):
    """Format a number with the document's decimal mark and thousands separator."""
    return f"{v:,.{dec}f}".replace(",", "\0").replace(".", DECIMAL).replace("\0", THOUSANDS)


def text(x, y, s, size=11, fill=INK2, weight=400, anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size * T:.1f}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{s}</text>')


def hbar(x0, y, length, h, color, r=4):
    """Horizontal bar: square base at x0, data end rounded by r px."""
    if length < 0.5:
        return ""
    r = min(r, length, h / 2)
    x1 = x0 + length
    return (f'<path d="M{x0:.1f},{y:.1f} H{x1 - r:.1f} A{r},{r} 0 0 1 {x1:.1f},{y + r:.1f} '
            f'V{y + h - r:.1f} A{r},{r} 0 0 1 {x1 - r:.1f},{y + h:.1f} H{x0:.1f} Z" fill="{color}"/>')


def dot(x, y, r=4, color=INK):
    """A marker with a 2 px ring in the surface colour, so it stays readable over bars and lines."""
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" '
            f'stroke="{SURFACE}" stroke-width="2"/>')


def legend(items, x, y):
    """items: (color, label, shape). A colour mark sits beside the text; the text stays in ink."""
    out, cx = [], x
    for color, label, shape in items:
        if shape == "dot":
            out.append(dot(cx + 5, y - 4))
        else:
            out.append(f'<rect x="{cx}" y="{y - 9}" width="10" height="10" rx="2" fill="{color}"/>')
        out.append(text(cx + 16, y, label, 11))
        cx += 16 + len(label) * 6.3 * T + 18
    return out


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            + "".join(body) + "</svg>")


def axis_ticks(x0, width, top, bottom, vmax, ticks, fmt):
    """Vertical hairline grid with tick labels under it, and the baseline axis at x0."""
    out = []
    for t in ticks:
        x = x0 + width * t / vmax
        out.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="{GRID}" stroke-width="1"/>')
        out.append(text(x, bottom + 14, fmt(t), 10, INK2, anchor="middle"))
    out.append(f'<line x1="{x0}" y1="{top}" x2="{x0}" y2="{bottom}" stroke="{AXIS}" stroke-width="1"/>')
    return out


# --- Chart 1: a value over time against a hard limit -------------------------
SERIES_A = [14.0, 20.06, 21.43, 25.07, 32.41, 46.73, 47.08]  # stops early: it hit the limit
SERIES_B = [12.39, 16.71, 19.21, 21.54, 24.78, 32.07, 40.14, 41.08, 40.52, 41.55, 40.63, 40.61,
            41.28, 41.29, 41.24, 41.62, 41.13, 40.75, 41.35, 41.69, 41.84]


def fig_line_limit():
    W, H, x0, x1, top, bot = 780, 270, 52, 570, 40, 220
    vmax, tmax, limit = 50, 20, 48
    X = lambda t: x0 + (x1 - x0) * t / tmax
    Y = lambda v: bot - (bot - top) * v / vmax
    b = legend([(ORANGE, "Config A", "square"), (BLUE, "Config B", "square")], x0, 16)
    for v in range(0, 51, 10):
        b.append(f'<line x1="{x0}" y1="{Y(v):.1f}" x2="{x1}" y2="{Y(v):.1f}" stroke="{GRID}"/>')
        b.append(text(x0 - 8, Y(v) + 4, str(v), 10, INK2, anchor="end"))
    for t in range(0, 21, 5):
        b.append(text(X(t), bot + 16, str(t), 10, INK2, anchor="middle"))
    b.append(f'<line x1="{x0}" y1="{bot}" x2="{x1}" y2="{bot}" stroke="{AXIS}"/>')
    b.append(text((x0 + x1) / 2, bot + 34, "seconds since the load started", 10.5, INK2, anchor="middle"))
    b.append(text(x0 - 8, top - 10, "MiB", 10, INK2, anchor="end"))
    # a hard limit: solid reference line in secondary ink, labelled
    b.append(f'<line x1="{x0}" y1="{Y(limit):.1f}" x2="{x1}" y2="{Y(limit):.1f}" stroke="{INK2}" stroke-width="1.5"/>')
    b.append(text(x1 + 8, Y(limit) + 4, f"limit {limit} MiB", 11, INK2))
    for series, color in ((SERIES_A, ORANGE), (SERIES_B, BLUE)):
        pts = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in enumerate(series))
        b.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
                 f'stroke-linejoin="round" stroke-linecap="round"/>')
        b.append(dot(X(len(series) - 1), Y(series[-1]), color=color))
    # direct labels: text in ink, identity from the colour mark beside it
    b.append(text(x1 + 8, Y(SERIES_B[-1]) + 14, "41.8 MiB, stable", 11))
    xl, yl = X(7.2), Y(33)  # free space below the blue line
    b.append(f'<rect x="{xl - 16:.1f}" y="{yl - 9:.1f}" width="10" height="10" rx="2" fill="{ORANGE}"/>')
    b.append(text(xl, yl, "47.1 MiB, then stopped", 11))
    b.append(text(xl, yl + 14, "(out of memory)", 11))
    return svg(W, H, b)


# --- Chart 2: two variants, repeated runs, one panel per metric --------------
# Each value is [run 1, run 2]. Key: (load level, variant).
RUNS = {
    ("Low", "Variant A"): {"rate": [981.44, 613.36], "mean": [10, 16], "peak": [941, 200]},
    ("Low", "Variant B"): {"rate": [302.49, 422.25], "mean": [33, 24], "peak": [295, 299]},
    ("High", "Variant A"): {"rate": [603.77, 677.06], "mean": [33, 29], "peak": [4145, 2640]},
    ("High", "Variant B"): {"rate": [492.83, 369.75], "mean": [40, 54], "peak": [200, 599]},
}
PANELS = [("rate", "Requests per second", "higher is better", 1000, [0, 500, 1000]),
          ("mean", "Mean time (ms)", "lower is better", 60, [0, 30, 60]),
          ("peak", "Maximum time (ms)", "lower is better", 4500, [0, 2000, 4000])]


def fig_grouped_runs():
    W, H, lab, pw, bh = 720, 300, 128, 128, 20
    b = legend([(BLUE, "Variant A", "square"), (ORANGE, "Variant B", "square"),
                (INK, "each run (bar = mean of the two)", "dot")], lab, 16)
    top = 78
    for pi, (key, title, hint, vmax, ticks) in enumerate(PANELS):
        x0 = 150 + pi * 190
        b.append(text(x0, 44, title, 12, INK, 600))
        b.append(text(x0, 58, hint, 10, INK2))
        b += axis_ticks(x0, pw, top, top + 2 * 100 - 16, vmax, ticks, lambda t: num(t))
        for gi, load in enumerate(("Low", "High")):
            gy = top + gi * 100
            if pi == 0:
                b.append(text(20, gy + 6, f"{load} load", 11.5, INK, 600))
            for ri, variant in enumerate(("Variant A", "Variant B")):
                y = gy + 16 + ri * 34
                runs = RUNS[(load, variant)][key]
                mean = sum(runs) / 2
                color = BLUE if variant == "Variant A" else ORANGE
                if pi == 0:
                    b.append(text(lab - 10, y + 15, variant, 11, INK2, anchor="end"))
                b.append(hbar(x0, y, pw * mean / vmax, bh, color))
                for r in runs:
                    b.append(dot(x0 + pw * r / vmax, y + bh / 2))
                tip = x0 + pw * max(mean, *runs) / vmax + 10
                b.append(text(tip, y + 15, num(mean), 11, INK, 600))
    return svg(W, H, b)


# --- Chart 3: peaks per component, two panels, limit lines -------------------
SCENARIOS = ["Variant A, low load", "Variant B, low load",
             "Variant A, high load", "Variant B, high load"]
CPU = [(26.3, 24.8, 46.1), (25.9, 0.0, 0.5), (26.3, 24.3, 37.4), (27.0, 0.5, 0.3)]
MEM = [(35.2, 28.0, 39.5), (33.6, 23.0, 35.9), (43.6, 33.1, 43.6), (43.3, 26.4, 40.8)]


def fig_paired_panels():
    W, H, lab, pw, bh, gap = 720, 400, 170, 130, 12, 2
    colors = [BLUE, ORANGE, AQUA]
    b = legend([(BLUE, "Component 1", "square"), (ORANGE, "Component 2", "square"),
                (AQUA, "Component 3 (no limit)", "square")], lab, 16)
    top, group = 78, 74
    bottom = top + 4 * group - 14
    panels = [("Peak CPU (% of one core)", CPU, 60, [0, 20, 40, 60], 25, "limit 25 %"),
              ("Peak memory (MiB)", MEM, 60, [0, 20, 40, 60], 48, "limit 48 MiB")]
    for pi, (title, data, vmax, ticks, limit, limit_txt) in enumerate(panels):
        x0 = lab + pi * 270
        b.append(text(x0, 46, title, 12, INK, 600))
        b += axis_ticks(x0, pw, top, bottom, vmax, ticks, lambda t: num(t))
        lx = x0 + pw * limit / vmax
        b.append(f'<line x1="{lx:.1f}" y1="{top - 6}" x2="{lx:.1f}" y2="{bottom}" stroke="{INK2}" stroke-width="1.5"/>')
        b.append(text(lx, top - 12, limit_txt, 10, INK2, anchor="middle"))
        for si, vals in enumerate(data):
            gy = top + si * group
            if pi == 0:
                name, load = SCENARIOS[si].split(", ")
                b.append(text(lab - 12, gy + 24, name, 11.5, INK, 600, "end"))
                b.append(text(lab - 12, gy + 38, load, 10.5, INK2, anchor="end"))
            for k, v in enumerate(vals):
                y = gy + 4 + k * (bh + gap)
                b.append(hbar(x0, y, pw * v / vmax, bh, colors[k], r=3))
                # surface-coloured backing so a value never fights a limit line or the grid
                lw = len(num(v, 1)) * 5.8 * T + 4
                b.append(f'<rect x="{x0 + pw * v / vmax + 5:.1f}" y="{y}" width="{lw:.1f}" height="{bh}" fill="{SURFACE}"/>')
                b.append(text(x0 + pw * v / vmax + 7, y + 10, num(v, 1), 10, INK))
    return svg(W, H, b)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, fn in (("line-limit", fig_line_limit), ("grouped-runs", fig_grouped_runs),
                     ("paired-panels", fig_paired_panels)):
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
        print("wrote", OUT / f"{name}.svg")
