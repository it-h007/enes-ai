"""Session cart (C-27). The session only stores {product_id: qty}; every price, stock
limit and total is recomputed from the database on each request (server authoritative)."""
from flask import current_app, session

from . import settings as st
from .catalog import products_by_ids
from .totals import totals


class CartError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def _raw():
    c = session.get("cart")
    return dict(c) if isinstance(c, dict) else {}


def _save(c):
    session["cart"] = {k: int(v) for k, v in c.items() if int(v) > 0}
    session.permanent = True
    session.modified = True


def max_qty(p, raw=None):
    cap = current_app.config["MAX_QTY_PER_LINE"]
    if raw is not None and raw["allow_backorder"]:
        return cap
    return max(0, min(cap, p["qty"]))


def purchasable(p, raw):
    if not raw["visible"] or not raw["cat_visible"]:
        return False, "hidden"
    if p["cat_adult"] and not current_app.config["ADULT_CHECKOUT_ENABLED"]:
        return False, "adult"
    if max_qty(p, raw) <= 0:
        return False, "out"
    return True, ""


def lines():
    """[(product_view, qty, max)] for items still purchasable; quantities clamped to stock."""
    c = _raw()
    if not c:
        return []
    found = products_by_ids(list(c.keys()))
    out, changed = [], False
    for pid, qty in c.items():
        hit = found.get(int(pid))
        if not hit:
            changed = True
            continue
        p, raw = hit
        ok, _ = purchasable(p, raw)
        if not ok:
            changed = True
            continue
        m = max_qty(p, raw)
        q = max(1, min(int(qty), m))
        if q != qty:
            changed = True
        out.append((p, q, m))
    if changed:
        _save({str(p["id"]): q for p, q, _ in out})
    return out


def count():
    return sum(int(v) for v in _raw().values())


def add(pid, qty=1):
    hit = products_by_ids([pid]).get(int(pid))
    if not hit:
        raise CartError("missing", "Produkti nuk u gjet.")
    p, raw = hit
    ok, why = purchasable(p, raw)
    if not ok:
        msg = {"hidden": "Produkti nuk është më në dyqan.", "out": "Produkti është përkohësisht jashtë stoku.",
               "adult": "Ky produkt nuk shitet online për momentin."}[why]
        raise CartError(why, msg)
    c = _raw()
    cur = int(c.get(str(pid), 0))
    m = max_qty(p, raw)
    new = min(m, cur + max(1, int(qty)))
    c[str(pid)] = new
    _save(c)
    return {"product": p, "qty": new, "capped": cur + int(qty) > m, "max": m}


def set_qty(pid, qty):
    c = _raw()
    if str(pid) not in c:
        raise CartError("missing", "Produkti nuk është në shportë.")
    qty = int(qty)
    if qty <= 0:
        c.pop(str(pid), None)
        _save(c)
        return 0
    hit = products_by_ids([pid]).get(int(pid))
    if not hit:
        c.pop(str(pid), None)
        _save(c)
        raise CartError("missing", "Produkti nuk u gjet.")
    p, raw = hit
    q = max(1, min(qty, max_qty(p, raw)))
    c[str(pid)] = q
    _save(c)
    return q


def remove(pid):
    c = _raw()
    c.pop(str(pid), None)
    _save(c)


def clear():
    _save({})


def cart_totals(ls=None, coupon_pct=0):
    ls = lines() if ls is None else ls
    s = st.all_settings()
    return totals([(p["price"], q) for p, q, _ in ls], coupon_pct, st.int_setting("fee", 0, s), st.int_setting("freeOver", 0, s))
