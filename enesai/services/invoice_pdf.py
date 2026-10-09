"""Server-side invoice PDF (ReportLab) — port of the prototype's jsPDF layout
(CODEX_IMPLEMENTATION_MAP §7.1). Uses ONLY the order row, its items and the seller
snapshot stored with the order, so old invoices never change when Settings change.
Title is “FATURË POROSIE”: an order invoice, not a fiscalised tax invoice (C-12)."""
import json
from pathlib import Path

from flask import current_app
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.lib.colors import Color
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from ..db import get_db
from ..util import fmt_date, fmt_time, lek_plain, maps_url
from . import orders as ordersvc

ASSETS = Path(__file__).resolve().parent.parent / "pdf_assets"
W_MM, H_MM, M = 210, 297, 16
R = W_MM - M

_fonts = False


def _register_fonts():
    global _fonts
    if _fonts:
        return
    pdfmetrics.registerFont(TTFont("Inter", str(ASSETS / "Inter-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Inter-Bold", str(ASSETS / "Inter-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Jakarta", str(ASSETS / "Jakarta-ExtraBold.ttf")))
    _fonts = True


def rgb(r, g, b):
    return Color(r / 255, g / 255, b / 255)


INK, GRAY, GOLD, GOLD7 = rgb(11, 11, 11), rgb(107, 107, 107), rgb(255, 196, 0), rgb(121, 88, 0)
PAPER, GREEN, RULE, WHITE = rgb(247, 246, 242), rgb(21, 128, 61), rgb(230, 228, 221), rgb(255, 255, 255)


def money(n):
    return lek_plain(n)


FALLBACK = {"›": ">", "‹": "<", "→": "->", "←": "<-", "–": "-", "—": "-", "…": "...", "\u00a0": " "}


class _Canvas(rl_canvas.Canvas):
    """Canvas that knows the page count when it draws the footer (‘Faqja x/y’ on every page)."""

    def __init__(self, *a, footer=None, **k):
        super().__init__(*a, **k)
        self._pages, self._footer = [], footer

    def _safe(self, text):
        """Replace characters the embedded font cannot draw (user-entered names) instead of
        printing empty boxes."""
        f = pdfmetrics.getFont(self._fontname)
        cmap = getattr(getattr(f, "face", None), "charToGlyph", None)
        if not cmap:
            return text
        return "".join(ch if ord(ch) in cmap or ch in " \n" else FALLBACK.get(ch, "?") for ch in str(text))

    def drawString(self, x, y, text, *a, **k):
        return super().drawString(x, y, self._safe(text), *a, **k)

    def drawRightString(self, x, y, text, *a, **k):
        return super().drawRightString(x, y, self._safe(text), *a, **k)

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._pages)
        for i, state in enumerate(self._pages, 1):
            self.__dict__.update(state)
            if self._footer:
                self._footer(self, i, n)
            super().showPage()
        super().save()


def build(order, items, snap, out):
    _register_fonts()
    url = maps_url(order["lat"], order["lng"])
    d_date, d_time = fmt_date(order["created_at"]), fmt_time(order["created_at"], True)
    trade = snap.get("tradeName") or "ENES’AI Super Market"

    def footer(c, page, pages):
        c.setStrokeColor(RULE); c.setLineWidth(0.2 * mm); c.line(M * mm, Y(282), R * mm, Y(282))
        font(c, "Inter", 7.5, GRAY)
        c.drawString(M * mm, Y(287), trade + (" · " + snap["web"] if snap.get("web") else ""))
        c.drawRightString(R * mm, Y(287), "Nr. %s · %s %s · Faqja %d/%d" % (order["nr"], d_date, d_time, page, pages))

    c = _Canvas(str(out), pagesize=(W_MM * mm, H_MM * mm), footer=footer, pageCompression=1)
    c.setTitle("Fatura " + order["nr"]); c.setSubject("Faturë porosie"); c.setAuthor(trade); c.setCreator("ENES’AI")

    def ph(v, label):
        return v if v else "[" + label + "]"

    y = 16
    # 1 · header: logo + seller (from the snapshot)
    logo = ASSETS / "enesai-logo-print.png"
    lw = 54
    lh = lw * 160 / 624
    c.drawImage(ImageReader(str(logo)), M * mm, Y(y + lh), lw * mm, lh * mm, mask="auto")
    font(c, "Inter-Bold", 10, INK); c.drawRightString(R * mm, Y(y + 3), ph(snap.get("legalName"), "Emri ligjor — Paneli > Cilësimet"))
    font(c, "Inter", 8.5, GRAY)
    c.drawRightString(R * mm, Y(y + 8), "NIPT: " + ph(snap.get("nipt"), "NIPT"))
    c.drawRightString(R * mm, Y(y + 12.5), ph(snap.get("address"), "Adresa") + ", " + (snap.get("city") or "Vlorë"))
    c.drawRightString(R * mm, Y(y + 17), "Tel: " + ph(snap.get("phone"), "Telefoni") + (" · " + snap["email"] if snap.get("email") else ""))
    y += 24
    c.setFillColor(GOLD); c.rect(M * mm, Y(y + 1.1), (R - M) * mm, 1.1 * mm, stroke=0, fill=1)

    # 2 · title row
    y += 9
    spaced(c, "FATURË POROSIE", M, y, "Jakarta", 8, GOLD7, 0.6)
    font(c, "Jakarta", 22, INK); c.drawString(M * mm, Y(y + 9), order["nr"])
    for x, (lab, val) in zip((R - 92, R - 62, R - 36), (("DATA", d_date), ("ORA", d_time), ("PAGESA", "Cash në dorëzim"))):
        font(c, "Inter-Bold", 7, GRAY); c.drawString(x * mm, Y(y + 2), lab)
        font(c, "Inter-Bold", 10, INK); c.drawString(x * mm, Y(y + 8), val)

    # 3 · parties
    y += 17
    bh, bw1, bw2 = 34, 46, 52
    bw3 = R - M - bw1 - bw2 - 8
    c.setFillColor(PAPER)
    c.roundRect(M * mm, Y(y + bh), bw1 * mm, bh * mm, 2 * mm, stroke=0, fill=1)
    c.roundRect((M + bw1 + 4) * mm, Y(y + bh), bw2 * mm, bh * mm, 2 * mm, stroke=0, fill=1)

    def box(x, w, title, lines):
        spaced(c, title, x + 4, y + 6, "Jakarta", 7, GRAY, 0.4)
        yy = y + 12
        for i, line in enumerate(lines):
            fn = "Inter-Bold" if i == 0 else "Inter"
            for part in simpleSplit(line, fn, 9, (w - 8) * mm):
                if yy < y + bh - 1:
                    font(c, fn, 9, INK if i == 0 else rgb(60, 60, 60)); c.drawString((x + 4) * mm, Y(yy), part)
                    yy += 4.3

    box(M, bw1, "KLIENTI", [order["name"] + " " + order["surname"], order["phone"]] + ([order["email"]] if order["email"] else []))
    box(M + bw1 + 4, bw2, "ADRESA E DËRGESËS", [order["address"], ordersvc.place_of(order)] + (["“" + order["courier_note"] + "”"] if order["courier_note"] else []))
    lx = M + bw1 + bw2 + 8
    c.setFillColor(INK); c.roundRect(lx * mm, Y(y + bh), bw3 * mm, bh * mm, 2 * mm, stroke=0, fill=1)
    qs = 24
    c.setFillColor(WHITE); c.roundRect((lx + 4) * mm, Y(y + 4 + qs + 2), (qs + 2) * mm, (qs + 2) * mm, 1 * mm, stroke=0, fill=1)
    w = QrCodeWidget(url, barLevel="M"); w.draw(); q = w.qr; n = q.getModuleCount(); cell = qs / n
    c.setFillColor(INK)
    for r in range(n):
        for col in range(n):
            if q.isDark(r, col):
                c.rect((lx + 5 + col * cell) * mm, Y(y + 5 + (r + 1) * cell), (cell + 0.02) * mm, (cell + 0.02) * mm, stroke=0, fill=1)
    tx = lx + qs + 9
    spaced(c, "VENDNDODHJA", tx, y + 8, "Jakarta", 7, GOLD, 0.4)
    font(c, "Inter-Bold", 9.5, WHITE); c.drawString(tx * mm, Y(y + 14.5), "Hap në Google Maps")
    tw = pdfmetrics.stringWidth("Hap në Google Maps", "Inter-Bold", 9.5)
    c.setStrokeColor(WHITE); c.setLineWidth(0.25 * mm); c.line(tx * mm, Y(y + 15.5), tx * mm + tw, Y(y + 15.5))
    c.linkURL(url, (tx * mm, Y(y + 17), tx * mm + max(tw, 40 * mm), Y(y + 10)), relative=0, thickness=0)
    c.linkURL(url, ((lx + 4) * mm, Y(y + 4 + qs + 2), (lx + 4 + qs + 2) * mm, Y(y + 4)), relative=0, thickness=0)
    font(c, "Inter", 7.5, rgb(168, 168, 168))
    c.drawString(tx * mm, Y(y + 21), "%.5f, %.5f" % (order["lat"], order["lng"]))
    c.drawString(tx * mm, Y(y + 25), "Zgjedhur në hartë" if order["loc_source"] == "map" else "GPS ±%s m" % (order["accuracy_m"] or "—"))
    c.drawString(tx * mm, Y(y + 29.5), "Skanoni ose prekni lidhjen")

    # 4 · items
    y += bh + 10
    cols = {"n": M, "name": M + 8, "qty": R - 52, "price": R - 26, "total": R}

    def head(y):
        font(c, "Inter-Bold", 7, GRAY)
        c.drawString(cols["n"] * mm, Y(y), "#"); c.drawString(cols["name"] * mm, Y(y), "PRODUKTI")
        c.drawRightString(cols["qty"] * mm, Y(y), "SASIA"); c.drawRightString(cols["price"] * mm, Y(y), "ÇMIMI")
        c.drawRightString(cols["total"] * mm, Y(y), "VLERA")
        y += 2.5
        c.setStrokeColor(INK); c.setLineWidth(0.4 * mm); c.line(M * mm, Y(y), R * mm, Y(y))
        return y + 5.5

    y = head(y)
    for i, it in enumerate(items):
        if y > 252:
            c.showPage(); y = head(20)
        font(c, "Inter", 9, GRAY); c.drawString(cols["n"] * mm, Y(y), str(i + 1))
        name = simpleSplit(it["name"], "Inter-Bold", 9.5, (cols["qty"] - cols["name"] - 14) * mm)[0]
        font(c, "Inter-Bold", 9.5, INK); c.drawString(cols["name"] * mm, Y(y), name)
        font(c, "Inter", 7.5, GRAY); c.drawString(cols["name"] * mm, Y(y + 4), "%s · %s" % (it["pack"], it["sku"]))
        font(c, "Inter", 9.5, INK)
        c.drawRightString(cols["qty"] * mm, Y(y), str(it["qty"])); c.drawRightString(cols["price"] * mm, Y(y), money(it["unit_price"]))
        font(c, "Inter-Bold", 9.5, INK); c.drawRightString(cols["total"] * mm, Y(y), money(it["unit_price"] * it["qty"]))
        y += 7
        c.setStrokeColor(RULE); c.setLineWidth(0.2 * mm); c.line(M * mm, Y(y), R * mm, Y(y))
        y += 5

    # 5 · totals + 6 · notes
    if y > 225:
        c.showPage(); y = 20
    y += 2
    ty, tw_, tx0 = y, 74, R - 74

    def row(a, b, col=None):
        nonlocal ty
        font(c, "Inter", 9.5, col or GRAY); c.drawString(tx0 * mm, Y(ty), a)
        font(c, "Inter-Bold", 9.5, col or INK); c.drawRightString(R * mm, Y(ty), b)
        ty += 6

    row("Nëntotali (%d artikuj)" % order["items_count"], money(order["subtotal"]))
    if order["discount"]:
        row("Kuponi %s (−%d%%)" % (order["coupon_code"], order["coupon_pct"]), "−" + money(order["discount"]), GREEN)
    row("Dërgesa", money(order["delivery"]) if order["delivery"] else "Falas")
    c.setFillColor(INK); c.roundRect(tx0 * mm, Y(ty - 2 + 12), tw_ * mm, 12 * mm, 2 * mm, stroke=0, fill=1)
    font(c, "Inter-Bold", 9, WHITE); c.drawString((tx0 + 4) * mm, Y(ty + 5.5), "Totali për t’u paguar")
    font(c, "Jakarta", 15, GOLD); c.drawRightString((R - 4) * mm, Y(ty + 6), money(order["total"]))
    ny, nw = y - 4, tx0 - M - 8
    if order["coupon_code"]:
        c.setStrokeColor(GOLD7); c.setDash(1.2 * mm, 1 * mm); c.setFillColor(rgb(255, 244, 204)); c.setLineWidth(0.25 * mm)
        c.roundRect(M * mm, Y(ny + 10), nw * mm, 10 * mm, 1.5 * mm, stroke=1, fill=1); c.setDash()
        font(c, "Inter", 8.5, INK); c.drawString((M + 4) * mm, Y(ny + 6.3), "Kuponi i përdorur: ")
        cw = pdfmetrics.stringWidth("Kuponi i përdorur: ", "Inter", 8.5)
        font(c, "Inter-Bold", 8.5, INK); c.drawString((M + 4) * mm + cw, Y(ny + 6.3), "%s  ·  −%d%%  ·  një përdorim" % (order["coupon_code"], order["coupon_pct"]))
        ny += 15
    font(c, "Inter", 8, GRAY)
    for line in simpleSplit(snap.get("note") or "", "Inter", 8, nw * mm):
        c.drawString(M * mm, Y(ny + 3), line); ny += 4
    c.showPage()
    c.save()


def Y(y_mm):
    return (H_MM - y_mm) * mm


def font(c, name, size, color):
    c.setFont(name, size); c.setFillColor(color)


def spaced(c, text, x_mm, y_mm, fname, size, color, space_mm):
    t = c.beginText(x_mm * mm, Y(y_mm))
    t.setFont(fname, size); t.setFillColor(color); t.setCharSpace(space_mm * mm)
    t.textOut(text)
    t.setCharSpace(0)  # Tc persists in the PDF text state: reset it
    c.drawText(t)


def ensure_pdf(order, con=None):
    """Generate once per order (immutable snapshot) and store privately; returns the path."""
    con = con or get_db()
    base = Path(current_app.config["PRIVATE_DIR"]) / "invoices"
    base.mkdir(parents=True, exist_ok=True)
    path = base / ("%s.pdf" % order["nr"])
    if not path.exists():
        items = ordersvc.items(order, con)
        snap = json.loads(order["seller_snapshot"])
        tmp = path.with_suffix(".tmp")
        build(order, items, snap, tmp)
        tmp.replace(path)
        con.execute("UPDATE orders SET pdf_path = ? WHERE id = ?", (path.name, order["id"]))
    return path
