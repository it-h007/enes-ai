"""Key/value store settings (admin › Cilësimet). Unverified store facts default to ''
so that public pages hide them (production rule V1-14 / C-16) — never invented."""
import json

from flask import g

from ..db import get_db

DEFAULT_NOTE = ("Faleminderit që zgjodhët ENES’AI! Ky dokument konfirmon porosinë online. "
                "Fatura tatimore lëshohet nga marketi në momentin e pagesës.")

DEFAULTS = {
    # brand
    "tradeName": "ENES’AI Super Market",
    "short": "EnesAi Market",
    "logo_dark": "",            # uploaded PNG overrides the bundled SVG
    "logo_light": "",
    # invoice & WhatsApp (DD-03)
    "legalName": "",
    "nipt": "",
    "whatsapp": "",
    "waMode": "manual",
    "prefix": "EA",
    "web": "",
    "note": DEFAULT_NOTE,
    # contact
    "phone": "",
    "email": "",
    "address": "",
    "hours": "",
    "hours_json": "",
    "city": "Vlorë",
    # location
    "store_lat": "",
    "store_lng": "",
    "maps_link": "",
    # delivery (V1-09 demo values — confirm with the store, C-15)
    "fee": "200",
    "freeOver": "3000",
    "delivery_area": "Vlorë",
    "zones": "Lungomare\nSkelë\nUji i Ftohtë\nQendër\nPavarësia\nTjetër",
    "delivery_demo": "1",
    # offers banner validity (content, P-06)
    "offers_until": "",
    # social (only real profiles are shown)
    "facebook": "",
    "instagram": "",
    "tiktok": "",
    # admin
    "session_timeout": "30",
    # NEOX credit (C-14 — numbers transcribed from the reference; confirm)
    "studio_call": "+355 68 550 3591",
    "studio_wa": "+44 775 156 4698",
}

SESSION_TIMEOUTS = {"30": "30 minutash pa aktivitet", "60": "1 ore", "480": "8 orësh"}


def all_settings(con=None):
    """All settings with defaults; cached per request unless an explicit connection is given."""
    cache = con is None
    if cache and "settings" in g:
        return g.settings
    s = dict(DEFAULTS)
    for r in (con or get_db()).execute("SELECT key, value FROM settings"):
        s[r["key"]] = r["value"]
    if cache:
        g.settings = s
    return s


def get(key, default=None):
    v = all_settings().get(key)
    return default if v in (None, "") and default is not None else v


def save(values, con=None):
    con = con or get_db()
    for k, v in values.items():
        con.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, "" if v is None else str(v)))
    g.pop("settings", None)


def int_setting(key, default=0, s=None):
    s = s or all_settings()
    try:
        return int(str(s.get(key, default)).replace(".", "").strip() or default)
    except ValueError:
        return default


def zones(s=None):
    s = s or all_settings()
    return [z.strip() for z in s.get("zones", "").splitlines() if z.strip()]


def hours_table(s=None):
    s = s or all_settings()
    try:
        data = json.loads(s.get("hours_json") or "[]")
    except ValueError:
        data = []
    days = ["Hënë", "Martë", "Mërkurë", "Enjte", "Premte", "Shtunë", "Diel"]
    out = []
    for i, d in enumerate(days):
        row = data[i] if i < len(data) and isinstance(data[i], dict) else {}
        out.append({"day": d, "open": row.get("open", ""), "close": row.get("close", ""), "closed": bool(row.get("closed"))})
    return out


def hours_text(s=None):
    """Public hours line: the free text wins, else built from the 7-day table."""
    s = s or all_settings()
    if s.get("hours"):
        return s["hours"]
    t = [r for r in hours_table(s) if r["open"] and r["close"] and not r["closed"]]
    if not t:
        return ""
    if len(t) == 7 and len({(r["open"], r["close"]) for r in t}) == 1:
        return "%s – %s" % (t[0]["open"], t[0]["close"])
    return ", ".join("%s %s–%s" % (r["day"][:3], r["open"], r["close"]) for r in t)


def seller_snapshot(s=None):
    """Seller data frozen into each order (invoice values never change afterwards)."""
    s = s or all_settings()
    keys = ["legalName", "tradeName", "nipt", "address", "city", "phone", "email", "web", "note", "whatsapp", "prefix"]
    return {k: s.get(k, "") for k in keys}


def missing_invoice_fields(s=None):
    s = s or all_settings()
    return [k for k in ("legalName", "nipt", "address", "phone", "whatsapp") if not s.get(k)]
