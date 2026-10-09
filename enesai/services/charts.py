"""Inline SVG charts — port of admin.lineChart / admin.barChart (30-admin.js:37–65). No chart library."""
from markupsafe import Markup, escape

from ..util import lek


def _k(v):
    return "%dk" % round(v / 1000) if v >= 1000 else str(round(v))


def line_chart(vals, prev=None, labels=None, label="Grafik", highlight=None):
    vals = [max(0, v) for v in vals] or [0]
    W, H, P = 640, 220, {"l": 44, "r": 12, "t": 16, "b": 28}
    mx = max(vals + (prev or []) + [1]) * 1.15
    n = max(1, len(vals) - 1)
    x = lambda i: P["l"] + i * (W - P["l"] - P["r"]) / n
    y = lambda v: P["t"] + (H - P["t"] - P["b"]) * (1 - v / mx)
    pts = ["%.1f,%.1f" % (x(i), y(v)) for i, v in enumerate(vals)]
    area = "M" + " L".join(pts) + " L%s,%s L%s,%s Z" % (x(len(vals) - 1), H - P["b"], P["l"], H - P["b"])
    grid, axis = [], []
    for gi in range(5):
        gv = mx * gi / 4
        gy = y(gv)
        grid.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f"/>' % (P["l"], W - P["r"], gy, gy))
        axis.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (P["l"] - 8, gy + 4, _k(gv)))
    for i, l in enumerate(labels or []):
        if l:
            axis.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x(i), H - 8, escape(l)))
    hi = len(vals) - 1 if highlight is None else highlight
    hx, hy = x(hi), y(vals[hi])
    prev_line = ('<polyline class="line line--prev" points="%s"/>' % " ".join("%.1f,%.1f" % (x(i), y(v)) for i, v in enumerate(prev))) if prev else ""
    return Markup(
        '<svg class="ea-chart" viewBox="0 0 %d %d" role="img" aria-label="%s"><defs><linearGradient id="ea-gold-fade" x1="0" x2="0" y1="0" y2="1">'
        '<stop offset="0" stop-color="#FFC400" stop-opacity=".32"/><stop offset="1" stop-color="#FFC400" stop-opacity="0"/></linearGradient></defs>'
        '<g class="grid">%s</g><g class="axis">%s</g>%s<path class="area" d="%s"/><polyline class="line" points="%s"/>'
        '<circle class="dot" cx="%.1f" cy="%.1f" r="5"/><g class="tip" transform="translate(%.1f,%.1f)"><rect width="92" height="26" rx="7"/>'
        '<text x="46" y="17" text-anchor="middle">%s</text></g></svg>'
        % (W, H, escape(label), "".join(grid), "".join(axis), prev_line, area, " ".join(pts), hx, hy, min(hx - 46, W - 104), hy - 38, lek(vals[hi])))


def bar_chart(a, b, labels, label="Porositë sipas ditës dhe mënyrës së pagesës"):
    W, H, P = 640, 220, {"l": 40, "r": 8, "t": 12, "b": 28}
    mx = max([x + y for x, y in zip(a, b)] + [1]) * 1.12
    bw = (W - P["l"] - P["r"]) / max(1, len(a))
    out, grid = [], []
    for gi in range(5):
        gy = P["t"] + (H - P["t"] - P["b"]) * gi / 4
        grid.append('<line x1="%d" x2="%d" y1="%s" y2="%s"/>' % (P["l"], W - P["r"], gy, gy))
    step = max(1, len(a) // 16)
    for i, v in enumerate(a):
        h1 = (H - P["t"] - P["b"]) * v / mx
        h2 = (H - P["t"] - P["b"]) * b[i] / mx
        x0, w = P["l"] + i * bw + bw * 0.2, bw * 0.6
        out.append('<rect class="bar" x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3"/>' % (x0, H - P["b"] - h1, w, h1))
        if b[i]:
            out.append('<rect class="bar bar--gold" x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3"/>' % (x0, H - P["b"] - h1 - h2 - 2, w, h2))
        if i % step == 0:
            out.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (x0 + w / 2, H - 8, escape(labels[i])))
    return Markup('<svg class="ea-chart" viewBox="0 0 %d %d" role="img" aria-label="%s"><g class="grid">%s</g><g class="axis">%s</g></svg>'
                  % (W, H, escape(label), "".join(grid), "".join(out)))
