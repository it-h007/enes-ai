"""QR codes without extra dependencies: ReportLab's encoder for both the PDF and the
inline SVG on the HTML invoice twin (DD-07)."""
from markupsafe import Markup
from reportlab.graphics.barcode.qr import QrCodeWidget


def matrix(text):
    w = QrCodeWidget(text, barLevel="M")
    w.draw()
    q = w.qr
    n = q.getModuleCount()
    return n, [[q.isDark(r, c) for c in range(n)] for r in range(n)]


def svg(text, cls="ea-qr"):
    """Same SVG shape as the design's qrSvg(): row runs as path segments, white quiet zone."""
    n, m = matrix(text)
    d = []
    for r in range(n):
        c = 0
        while c < n:
            if m[r][c]:
                s = c
                while c < n and m[r][c]:
                    c += 1
                d.append("M%d %dh%dv1h-%dz" % (s, r, c - s, c - s))
            else:
                c += 1
    return Markup('<svg class="%s" viewBox="-2 -2 %d %d" shape-rendering="crispEdges" role="img" aria-label="Kodi QR i vendndodhjes">'
                  '<rect x="-2" y="-2" width="%d" height="%d" fill="#fff"/><path fill="#0B0B0B" d="%s"/></svg>'
                  % (cls, n + 4, n + 4, n + 4, n + 4, "".join(d)))
