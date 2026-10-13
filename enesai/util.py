"""Shared helpers: money/date formatting, normalisation, rounding, icons."""
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from markupsafe import Markup, escape

TZ = ZoneInfo("Europe/Tirane")
NBSP = " "

# ---------------- time ----------------

def now():
    return datetime.now(TZ).replace(microsecond=0, tzinfo=None)


def now_iso():
    return now().isoformat(timespec="seconds")


def parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19])
    except ValueError:
        return None


def fmt_date(v):
    d = parse_dt(v)
    return d.strftime("%d.%m.%Y") if d else ""


def fmt_time(v, secs=False):
    d = parse_dt(v)
    return d.strftime("%H:%M:%S" if secs else "%H:%M") if d else ""


def fmt_dt(v, secs=False):
    d = parse_dt(v)
    return (fmt_date(d) + " " + fmt_time(d, secs)) if d else ""


# ---------------- money ----------------

def round_half_up(num, den=1):
    """Integer division rounding .5 up (same as JS Math.round for positives)."""
    num, den = int(num), int(den)
    return (2 * num + den) // (2 * den)


def lek(n):
    """2370 → '2.370 L' (dot thousands, NBSP, no decimals)."""
    try:
        n = int(round(float(n)))
    except (TypeError, ValueError):
        n = 0
    s = f"{abs(n):,}".replace(",", ".")
    return ("-" if n < 0 else "") + s + NBSP + "L"


def lek_plain(n):
    return lek(n).replace(NBSP, " ")


def discounted(price, pct):
    """New shop price = round(price × (1 − pct/100)), whole lek."""
    if not pct:
        return int(price)
    return round_half_up(int(price) * (100 - int(pct)), 100)


def num(n):
    return f"{int(n):,}".replace(",", ".")


# ---------------- text ----------------

_FOLD = str.maketrans({"ë": "e", "Ë": "e", "ç": "c", "Ç": "c", "é": "e", "è": "e"})


def norm(v):
    """Accent-insensitive, lower-case, single-spaced (ë→e, ç→c)."""
    s = str(v or "").translate(_FOLD).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def slugify(v):
    s = norm(v).replace("&", " ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "kategori"


def phone_digits(v):
    """Digits for search: +355 69… / 00355 69… / 069… → 069…"""
    d = re.sub(r"\D", "", str(v or ""))
    if d.startswith("00355"):
        d = "0" + d[5:]
    elif d.startswith("355") and len(d) >= 11:
        d = "0" + d[3:]
    return d


PHONE_AL = re.compile(r"^(?:\+355|00355|0)6[5-9]\d{7}$")
PHONE_INTL = re.compile(r"^\+\d{8,15}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._%+-]{0,62}[A-Za-z0-9_+-])?@[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*\.[A-Za-z]{2,24}$")


def clean_phone(v):
    return re.sub(r"[\s\-().]", "", str(v or ""))


def valid_phone(v):
    n = clean_phone(v)
    return bool(PHONE_AL.match(n) or PHONE_INTL.match(n))


def e164_digits(v):
    """Normalise a phone to WhatsApp/E.164 digits (no '+'). '069 123 4567' → '355691234567'.
    Fixes the prototype defect X8/C-33 (leading 0 was dropped without country code)."""
    n = clean_phone(v)
    if not n:
        return ""
    if n.startswith("+"):
        return re.sub(r"\D", "", n)
    n = re.sub(r"\D", "", n)
    if n.startswith("00"):
        return n[2:]
    if n.startswith("0"):
        return "355" + n[1:]
    if n.startswith("355"):
        return n
    if re.match(r"^6[5-9]\d{7}$", n):
        return "355" + n
    return n


def maps_url(lat, lng):
    return "https://www.google.com/maps/search/?api=1&query=%.6f,%.6f" % (float(lat), float(lng))


def wa_url(number_digits, text):
    """wa.me link; the whole text is percent-encoded so '&' inside the Maps URL cannot
    truncate or split the message."""
    return "https://wa.me/" + (number_digits or "") + "?text=" + quote(text, safe="")


def csv_safe(v):
    """Neutralise spreadsheet formula injection in exported cells."""
    s = "" if v is None else str(v)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


# ---------------- icons ----------------

_ICONS = json.loads((Path(__file__).parent / "data" / "icons.json").read_text(encoding="utf-8"))


def icon(name, cls=None):
    """Same output as the design's icon(): Lucide 0.460.0 paths inside .ea-icon SVG."""
    c = "ea-icon" + (" " + cls if cls else "")
    return Markup('<svg class="%s" viewBox="0 0 24 24" aria-hidden="true" focusable="false">%s</svg>'
                  % (escape(c), _ICONS.get(name, "")))


def has_icon(name):
    return name in _ICONS


def text_to_html(text):
    """Admin-entered body text → safe HTML. Everything is escaped; blank lines make
    paragraphs, '## ' makes a heading, '- ' lines make a list. No raw HTML is accepted."""
    out = []
    for block in re.split(r"\n\s*\n", str(text or "").replace("\r", "").strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if lines[0].startswith("## "):
            out.append(Markup('<h2 class="ea-h-title">%s</h2>') % lines[0][3:].strip())
            lines = lines[1:]
            if not lines:
                continue
        if all(l.lstrip().startswith("- ") for l in lines):
            out.append(Markup("<ul>%s</ul>") % Markup("").join(Markup("<li>%s</li>") % l.lstrip()[2:] for l in lines))
        else:
            out.append(Markup("<p>%s</p>") % Markup("<br>").join(escape(l) for l in lines))
    return Markup("").join(out)
