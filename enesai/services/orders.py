"""Order creation (FUNCTIONAL_REQUIREMENTS §2.11) and order state changes.

create_order() runs in ONE `BEGIN IMMEDIATE` transaction:
  re-read products + prices + stock → coupon redemption (atomic) → number allocation
  (per-prefix/per-year counter) → order + items with snapshots → stock decrement → commit.
Any failure rolls everything back, so a coupon or an order number is never half-used.
Idempotency: the checkout form carries a random key; a repeated POST with the same key
returns the existing order instead of creating a second one."""
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta

from flask import current_app

from ..db import get_db, transaction
from ..util import (EMAIL_RE, clean_phone, discounted, e164_digits, fmt_date, fmt_time, lek_plain, maps_url, norm, now,
                    now_iso, parse_dt, phone_digits, valid_phone)
from . import audit, coupons
from . import settings as st
from .totals import totals

STATUS = {"new": "E re", "prep": "Në përgatitje", "route": "Në rrugë", "done": "Dorëzuar", "cancel": "Anuluar"}
FLOW = ["new", "prep", "route", "done"]
LABELS = {"co-name": "Emri", "co-surname": "Mbiemri", "co-tel": "Telefoni", "co-mail": "Email-i", "co-loc": "Vendndodhja",
          "co-addr": "Adresa e plotë", "co-terms": "Kushtet"}


class OrderError(Exception):
    def __init__(self, code, detail=None):
        super().__init__(code)
        self.code, self.detail = code, detail


# ---------------- validation (same rules as the browser, FUNCTIONAL §2.10) ----------------

def validate(form):
    g_ = lambda k, n=200: (form.get(k) or "").strip()[:n]
    v = {"name": g_("name", 60), "surname": g_("surname", 60), "phone": g_("phone", 24), "email": g_("email", 254).lower(),
         "optin": form.get("optin") == "1", "city": g_("city", 60), "zone": g_("zone", 60), "address": g_("address", 200),
         "note": g_("note", 300), "terms": form.get("terms") == "1", "pay": form.get("pay") or "cash"}
    err = {}
    if len(v["name"]) < 2:
        err["co-name"] = "Shkruani emrin."
    if len(v["surname"]) < 2:
        err["co-surname"] = "Shkruani mbiemrin."
    if not clean_phone(v["phone"]):
        err["co-tel"] = "Shkruani numrin e telefonit, p.sh. 069 123 4567."
    elif not valid_phone(v["phone"]):
        err["co-tel"] = "Numri nuk duket i saktë. Shembull: 069 123 4567 ose +355 69 123 4567."
    if v["email"] and not EMAIL_RE.match(v["email"]):
        err["co-mail"] = "Email-i nuk duket i saktë (p.sh. emri@gmail.com) — ose lëreni bosh."
    loc = parse_location(form)
    if not loc:
        err["co-loc"] = "Zgjidhni pikën: GPS ose në hartë"
    elif not within_delivery_area(loc["lat"], loc["lng"]):
        err["co-loc"] = "Pika është jashtë zonës së dërgesës (Vlorë). Kontrolloni pikën në hartë"
        loc = None
    if len(v["address"]) < 6:
        err["co-addr"] = "Shkruani të paktën rrugën dhe pallatin / shtëpinë."
    if not v["terms"]:
        err["co-terms"] = "Pranoni kushtet e shitjes"
    if v["pay"] != "cash":
        err["co-pay"] = "Pagesa me kartë nuk është aktive."
    zones = st.zones()
    if v["zone"] and v["zone"] not in zones:
        v["zone"] = ""
    v["city"] = st.get("city") or "Vlorë"  # only the configured city is served
    return v, loc, err


def parse_location(form):
    """Required point from GPS or an explicitly confirmed map pin (CR-10). Typed coordinates
    are not offered in the UI; the server still range-checks whatever arrives."""
    try:
        lat, lng = float(form.get("lat", "")), float(form.get("lng", ""))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None
    src = form.get("loc_source")
    if src not in ("gps", "map"):
        return None
    acc = None
    if src == "gps":
        try:
            acc = max(0, min(100000, int(float(form.get("accuracy_m") or 0)))) or None
        except ValueError:
            acc = None
    return {"lat": round(lat, 6), "lng": round(lng, 6), "src": src, "acc": acc}


VLORE = (40.4660, 19.4914)


def store_center():
    s = st.all_settings()
    try:
        return (float(s["store_lat"]), float(s["store_lng"])) if s.get("store_lat") and s.get("store_lng") else VLORE
    except ValueError:
        return VLORE


def within_delivery_area(lat, lng):
    """Sanity bound: the point must be within MAX_DELIVERY_KM of the store (default 60 km),
    which rejects obviously wrong points (0,0, another country) without guessing zones."""
    import math
    clat, clng = store_center()
    dlat, dlng = math.radians(lat - clat), math.radians(lng - clng)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(clat)) * math.cos(math.radians(lat)) * math.sin(dlng / 2) ** 2
    km = 6371 * 2 * math.asin(math.sqrt(a))
    return km <= current_app.config.get("MAX_DELIVERY_KM", 60)


# ---------------- tokens for the confirmation page / PDF (C-28) ----------------

def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def token_ok(order, token):
    if not token or not order:
        return False
    if not hmac.compare_digest(_hash(token), order["access_token_hash"]):
        return False
    created = parse_dt(order["created_at"])
    return created is not None and now() - created <= timedelta(days=current_app.config["ORDER_LINK_DAYS"])


# ---------------- creation ----------------

def _allocate_number(con, prefix, year):
    con.execute("INSERT INTO order_counters(prefix, year, last) VALUES (?, ?, 0) ON CONFLICT(prefix, year) DO NOTHING", (prefix, year))
    con.execute("UPDATE order_counters SET last = last + 1 WHERE prefix = ? AND year = ?", (prefix, year))
    n = con.execute("SELECT last FROM order_counters WHERE prefix = ? AND year = ?", (prefix, year)).fetchone()[0]
    nr = "%s-%d-%05d" % (prefix, year, n)
    # safety net if the counter was ever reset by hand: skip numbers that exist
    while con.execute("SELECT 1 FROM orders WHERE nr = ?", (nr,)).fetchone():
        con.execute("UPDATE order_counters SET last = last + 1 WHERE prefix = ? AND year = ?", (prefix, year))
        n += 1
        nr = "%s-%d-%05d" % (prefix, year, n)
    return nr


def create_order(v, loc, cart_items, coupon_code, idem_key, con=None, is_demo=False, created_at=None):
    """cart_items: [(product_id, qty)]. Returns (order_row, token) or raises OrderError / CouponError."""
    con = con or get_db()
    if not idem_key or not re.match(r"^[A-Za-z0-9_-]{16,64}$", idem_key):
        raise OrderError("idem")
    existing = con.execute("SELECT * FROM orders WHERE idempotency_key = ?", (idem_key,)).fetchone()
    if existing:
        return existing, None
    if not cart_items:
        raise OrderError("empty")
    s = st.all_settings(con)
    prefix = re.sub(r"[^A-Z]", "", (s.get("prefix") or "EA").upper())[:4] or "EA"
    fee, free_over = st.int_setting("fee", 0, s), st.int_setting("freeOver", 0, s)
    cap = current_app.config["MAX_QTY_PER_LINE"]
    adult_ok = current_app.config["ADULT_CHECKOUT_ENABLED"]
    token = secrets.token_urlsafe(24)
    ts = created_at or now_iso()
    with transaction(con):
        again = con.execute("SELECT * FROM orders WHERE idempotency_key = ?", (idem_key,)).fetchone()
        if again:
            return again, None
        items, problems = [], []
        for pid, qty in cart_items:
            r = con.execute("""SELECT p.*, c.visible AS cat_visible, c.adult AS cat_adult,
                               (SELECT path FROM product_images i WHERE i.product_id = p.id ORDER BY sort, id LIMIT 1) AS image
                               FROM products p JOIN categories c ON c.id = p.category_id WHERE p.id = ?""", (int(pid),)).fetchone()
            qty = int(qty)
            if not r or not r["visible"] or not r["cat_visible"] or (r["cat_adult"] and not adult_ok):
                problems.append(("gone", r["name_sq"] if r else str(pid)))
                continue
            if qty < 1 or qty > cap or (not r["allow_backorder"] and r["stock"] < qty):
                problems.append(("stock", r["name_sq"]))
                continue
            items.append((r, qty))
        if problems:
            raise OrderError("cart_changed", problems)
        lines = [(discounted(r["price"], r["discount_pct"]), q) for r, q in items]
        pct = 0
        customer = v["name"] + " " + v["surname"]
        nr = _allocate_number(con, prefix, int(ts[:4]))
        if coupon_code:
            pct = coupons.redeem(con, coupons.normalize(coupon_code), nr, customer, ts)  # raises CouponError → rollback
        t = totals(lines, pct, fee, free_over)
        snap = st.seller_snapshot(s)
        search = norm(" ".join([nr, v["name"], v["surname"], v["surname"], v["name"], v["email"], coupon_code or "", v["address"]]))
        cur = con.execute(
            """INSERT INTO orders(nr, created_at, name, surname, phone, phone_digits, email, marketing_optin, optin_at, city, zone, address,
               courier_note, lat, lng, loc_source, accuracy_m, items_count, subtotal, coupon_code, coupon_pct, discount, delivery, total,
               payment, status, status_changed_at, seller_snapshot, access_token_hash, idempotency_key, search_norm, is_demo, wa_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'cash', 'new', ?, ?, ?, ?, ?, ?, ?)""",
            (nr, ts, v["name"], v["surname"], v["phone"], phone_digits(v["phone"]), v["email"], 1 if v["optin"] and v["email"] else 0,
             ts if v["optin"] and v["email"] else None, v["city"], v["zone"], v["address"], v["note"], loc["lat"], loc["lng"], loc["src"],
             loc["acc"], t["items"], t["sub"], coupons.normalize(coupon_code) if coupon_code else None, pct, t["discount"], t["fee"], t["total"],
             ts, json.dumps(snap, ensure_ascii=False), _hash(token), idem_key, search, 1 if is_demo else 0,
             "api_pending" if s.get("waMode") == "api" and wa_api_configured() else ""))
        oid = cur.lastrowid
        for r, q in items:
            con.execute("""INSERT INTO order_items(order_id, product_id, sku, name, pack, image, unit_price, list_price, discount_pct, qty)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (oid, r["id"], r["sku"], r["name_sq"], r["packaging"], r["image"] or "", discounted(r["price"], r["discount_pct"]),
                         r["price"], r["discount_pct"], q))
            c2 = con.execute("UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ? AND (allow_backorder = 1 OR stock >= ?)", (q, r["id"], q))
            if c2.rowcount != 1:
                raise OrderError("cart_changed", [("stock", r["name_sq"])])
        if v["optin"] and v["email"]:
            con.execute("""INSERT INTO subscribers(email, created_at, source, active, token) VALUES (?, ?, 'arka', 1, ?)
                           ON CONFLICT(email) DO UPDATE SET active = 1, unsubscribed_at = NULL""", (v["email"], ts, secrets.token_urlsafe(24)))
        audit.log("Porosi e re", "%s · %s" % (nr, lek_plain(t["total"])), area="orders", tone="new", con=con, operator=False)
        order = con.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
    current_app.logger.info("order created %s total=%s items=%s coupon=%s", nr, t["total"], t["items"], bool(coupon_code))
    return order, token


def wa_api_configured():
    c = current_app.config
    return bool(c.get("WA_TOKEN") and c.get("WA_PHONE_ID") and c.get("WA_TEMPLATE"))


# ---------------- reading ----------------

def get(nr, con=None):
    return (con or get_db()).execute("SELECT * FROM orders WHERE nr = ?", (nr,)).fetchone()


def items(order, con=None):
    return (con or get_db()).execute("SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall()


def place_of(o):
    return (o["zone"] + ", " if o["zone"] else "") + (o["city"] or "Vlorë")


def order_text(o, its):
    """WhatsApp invoice text (FUNCTIONAL §2.13, exact format)."""
    L = ["POROSI E RE — ENES’AI SUPER MARKET", "Nr. i faturës: " + o["nr"],
         "Data: " + fmt_date(o["created_at"]) + " · Ora: " + fmt_time(o["created_at"]), "",
         "Klienti: " + o["name"] + " " + o["surname"], "Telefoni: " + o["phone"]]
    if o["email"]:
        L.append("Email: " + o["email"])
    L.append("Adresa: " + o["address"] + ", " + place_of(o))
    if o["courier_note"]:
        L.append("Udhëzime: " + o["courier_note"])
    L += ["Vendndodhja: " + maps_url(o["lat"], o["lng"]), ""]
    for it in its:
        L.append("%d × %s (%s) — %s" % (it["qty"], it["name"], it["pack"], lek_plain(it["unit_price"] * it["qty"])))
    L += ["", "Nëntotali: " + lek_plain(o["subtotal"])]
    if o["discount"]:
        L.append("Kuponi %s (−%d%%): −%s" % (o["coupon_code"], o["coupon_pct"], lek_plain(o["discount"])))
    L.append("Dërgesa: " + (lek_plain(o["delivery"]) if o["delivery"] else "Falas"))
    L.append("TOTALI: " + lek_plain(o["total"]) + " · Cash në dorëzim")
    return "\n".join(L)


def courier_text(o):
    return "\n".join(["DËRGESË — " + o["nr"], o["name"] + " " + o["surname"] + " · " + o["phone"],
                      o["address"] + (", " + o["zone"] if o["zone"] else "") + ", " + (o["city"] or "Vlorë") + (" (" + o["courier_note"] + ")" if o["courier_note"] else ""),
                      "Harta: " + maps_url(o["lat"], o["lng"]), "Për t’u marrë: " + lek_plain(o["total"]) + " cash"])


def market_wa_digits(o=None):
    """Destination = the market's number. Snapshot first (number at order time), then current settings."""
    num = ""
    if o is not None:
        try:
            num = json.loads(o["seller_snapshot"]).get("whatsapp", "")
        except (ValueError, TypeError):
            num = ""
    return e164_digits(num or st.get("whatsapp") or "")


# ---------------- status changes ----------------

def change_status(nr, new_status, operator, con=None):
    """Flow E re → Në përgatitje → Në rrugë → Dorëzuar (any step) or → Anuluar.
    Cancel is final: it restores stock and returns the coupon (DD-06)."""
    con = con or get_db()
    if new_status not in STATUS:
        raise OrderError("bad_status")
    with transaction(con):
        o = con.execute("SELECT * FROM orders WHERE nr = ?", (nr,)).fetchone()
        if not o:
            raise OrderError("missing")
        if o["status"] == new_status:
            return o, False
        if o["status"] == "cancel":
            raise OrderError("cancelled_final")
        returned = False
        if new_status == "cancel":
            for it in con.execute("SELECT product_id, qty FROM order_items WHERE order_id = ?", (o["id"],)):
                if it["product_id"]:
                    con.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (it["qty"], it["product_id"]))
            if o["coupon_code"]:
                returned = coupons.give_back(con, o["coupon_code"], nr, operator)
        con.execute("UPDATE orders SET status = ?, status_changed_at = ? WHERE id = ?", (new_status, now_iso(), o["id"]))
        audit.log("Ndryshoi statusin", "Porosia %s" % nr, STATUS[o["status"]], STATUS[new_status] + (" · kuponi u rikthye" if returned else ""),
                  area="orders", tone="danger" if new_status == "cancel" else "info", con=con)
        o2 = con.execute("SELECT * FROM orders WHERE id = ?", (o["id"],)).fetchone()
    return o2, returned


def mark_wa_opened(nr, con=None):
    """Customer pressed the green button: we only know WhatsApp was opened with the text,
    not that the message was sent (that needs the Business API)."""
    con = con or get_db()
    con.execute("UPDATE orders SET wa_opened_at = COALESCE(wa_opened_at, ?) WHERE nr = ?", (now_iso(), nr))


# ---------------- invoice search (CR-14) ----------------

def search(q, status=None, limit=50, offset=0, con=None, date_from=None, date_to=None, zone=None):
    con = con or get_db()
    where, args = [], []
    if status:
        where.append("status = ?"); args.append(status)
    if date_from:
        where.append("created_at >= ?"); args.append(date_from)
    if date_to:
        where.append("created_at < ?"); args.append(date_to)
    if zone:
        where.append("zone = ?"); args.append(zone)
    nq = norm(q)
    if nq:
        digits = re.sub(r"\D", "", nq)
        ors = ["search_norm LIKE ? ESCAPE '\\'"]
        args_q = ["%" + nq.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"]
        if len(digits) >= 3:
            pd = phone_digits(digits) if not digits.startswith("0") else digits
            ors.append("phone_digits LIKE ?"); args_q.append("%" + pd.lstrip("0") + "%" if len(pd) > 3 else "%" + pd + "%")
            ors.append("REPLACE(nr, '-', '') LIKE ?"); args_q.append("%" + digits + "%")
        where.append("(" + " OR ".join(ors) + ")")
        args += args_q
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    total = con.execute("SELECT COUNT(*) FROM orders" + sql_where, args).fetchone()[0]
    rows = con.execute("SELECT * FROM orders" + sql_where + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    return rows, total
