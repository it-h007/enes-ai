"""One-time percentage coupons (CR-17/18/19). Created/cancelled only by the Owner or a
Manager holding the Kuponat permission (enforced in the admin routes). Redemption is
atomic inside the order transaction: a conditional UPDATE … WHERE status='active' can
succeed for one order only, so the same coupon can never be used twice."""
import re
import secrets

from flask import current_app

from ..db import get_db
from ..util import fmt_date, now, now_iso
from . import audit

CODE_RE = re.compile(r"^[A-Z0-9-]{4,20}$")
GEN_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O, 1/I/L


class CouponError(Exception):
    def __init__(self, code, used_on=None):
        super().__init__(code)
        self.code, self.used_on = code, used_on


def normalize(code):
    return re.sub(r"\s+", "", str(code or "")).upper()[:20]


def generate(con=None):
    con = con or get_db()
    for _ in range(50):
        c = "EA-" + "".join(secrets.choice(GEN_ALPHABET) for _ in range(6))
        if not con.execute("SELECT 1 FROM coupons WHERE code=?", (c,)).fetchone():
            return c
    raise RuntimeError("could not generate a unique coupon code")


def today():
    return now().date().isoformat()


def state(row):
    """active | used | expired | cancelled — 'expired' is derived from ends_on."""
    if row["status"] != "active":
        return row["status"]
    if row["ends_on"] and row["ends_on"] < today():
        return "expired"
    return "active"


def check(code, con=None):
    """Public check (no state change). Returns dict(ok, code, pct) or raises CouponError."""
    code = normalize(code)
    if not code:
        raise CouponError("empty")
    row = (con or get_db()).execute("SELECT * FROM coupons WHERE code = ?", (code,)).fetchone()
    if not row:
        raise CouponError("missing")
    st = state(row)
    if st != "active":
        raise CouponError(st, fmt_date(row["used_at"]) if st == "used" else None)
    return {"code": row["code"], "pct": row["pct"]}


def redeem(con, code, order_nr, customer_name, at=None):
    """Must run inside the order transaction. Atomic: 0 rows → raise, caller rolls back."""
    t = at or now_iso()
    cur = con.execute(
        "UPDATE coupons SET status='used', used_order_nr=?, used_by=?, used_at=? "
        "WHERE code=? AND status='active' AND (ends_on IS NULL OR ends_on = '' OR ends_on >= ?)",
        (order_nr, customer_name, t, code, today()))
    if cur.rowcount != 1:
        row = con.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
        raise CouponError(state(row) if row else "missing", fmt_date(row["used_at"]) if row and row["used_at"] else None)
    pct = con.execute("SELECT pct FROM coupons WHERE code=?", (code,)).fetchone()[0]
    con.execute("INSERT INTO coupon_events(code, event, order_nr, at, by_name) VALUES (?, 'used', ?, ?, ?)", (code, order_nr, t, customer_name))
    audit.log("Kupon i përdorur", "%s (−%d%%) · fatura %s" % (code, pct, order_nr), area="coupons", tone="success", con=con, operator=False)
    return pct


def give_back(con, code, order_nr, operator):
    """DD-06: cancelling an order returns its coupon (only if this order used it)."""
    cur = con.execute("UPDATE coupons SET status='active', used_order_nr=NULL, used_by=NULL, used_at=NULL "
                      "WHERE code=? AND status='used' AND used_order_nr=?", (code, order_nr))
    if cur.rowcount:
        con.execute("INSERT INTO coupon_events(code, event, order_nr, at, by_name) VALUES (?, 'returned', ?, ?, ?)",
                    (code, order_nr, now_iso(), operator["name"] if operator else "Sistemi"))
    return cur.rowcount == 1


def validate_new(code, pct, ends_on, con=None):
    code = normalize(code)
    errors = {}
    if not CODE_RE.match(code):
        errors["code"] = "Kodi duhet të ketë 4–20 shenja: shkronja A–Z, shifra ose vizë."
    elif (con or get_db()).execute("SELECT 1 FROM coupons WHERE code=?", (code,)).fetchone():
        errors["code"] = "Ky kod ekziston. Gjeneroni një tjetër ose ndryshojeni."
    maxp = current_app.config.get("COUPON_MAX_PCT", 90)
    try:
        pct = int(pct)
    except (TypeError, ValueError):
        pct = 0
    if not 1 <= pct <= min(90, maxp):
        errors["pct"] = "Zgjidhni zbritjen (1–%d%%)." % min(90, maxp)
    if ends_on:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", ends_on):
            errors["until"] = "Data nuk është e vlefshme."
        elif ends_on < today():
            errors["until"] = "Data e mbarimit është në të kaluarën."
    return code, pct, errors


def create(code, pct, ends_on, note, operator, con=None):
    con = con or get_db()
    code, pct, errors = validate_new(code, pct, ends_on, con)
    if errors:
        return None, errors
    t = now_iso()
    con.execute("INSERT INTO coupons(code, pct, status, created_by, created_by_name, created_at, ends_on, note) VALUES (?,?, 'active', ?,?,?,?,?)",
                (code, pct, operator["id"], operator["name"], t, ends_on or None, (note or "").strip()[:200]))
    con.execute("INSERT INTO coupon_events(code, event, at, by_name) VALUES (?, 'created', ?, ?)", (code, t, operator["name"]))
    audit.log("Krijoi kupon", "%s · −%d%%%s" % (code, pct, (" · deri " + fmt_date(ends_on)) if ends_on else ""), area="coupons", tone="new", con=con)
    return {"code": code, "pct": pct, "until": ends_on}, {}


def cancel(code, operator, con=None):
    con = con or get_db()
    cur = con.execute("UPDATE coupons SET status='cancelled', cancelled_at=? WHERE code=? AND status='active'", (now_iso(), normalize(code)))
    if cur.rowcount:
        con.execute("INSERT INTO coupon_events(code, event, at, by_name) VALUES (?, 'cancelled', ?, ?)", (normalize(code), now_iso(), operator["name"]))
        audit.log("Anuloi kupon", normalize(code), area="coupons", tone="danger", con=con)
    return cur.rowcount == 1
