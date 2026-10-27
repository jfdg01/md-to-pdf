# md-to-pdf

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `jfdg01/md-to-pdf`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Charts

Reports embed charts as SVG images. Read `docs/charts.md` before you make or change a chart: it has the workflow, the colour, mark and label rules, and a checklist. `docs/charts/example.py` is the reference generator.

## Infográficos

Lee `docs/infographics.md` antes de hacer o cambiar un infográfico: una figura que cuenta una prueba entera con iconos, tarjetas y cifras grandes, como una diapositiva.

## Las normas de las figuras

Las normas de `docs/` son el punto de partida, no un techo. Una forma mejor de hacer una figura entra en su doc, y cada figura nueva la sigue, para que todas las figuras sean iguales. Una figura sin norma escrita recibe un doc en `docs/` con lo que hiciste, y la próxima figura parte de él.

## Figure images

Read `docs/figures.md` before you add a screenshot or any PNG figure: the image carries no margin of its own (the tool draws the frame), and a window capture is cropped by its frame extents so every capture has the same edges.
