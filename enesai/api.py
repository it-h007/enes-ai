"""Cart, search, newsletter and coupon endpoints. Every POST is CSRF-checked (app-level).
fetch() callers get JSON; plain form posts (no JavaScript) get a redirect + flash."""
import secrets
from urllib.parse import urlparse

from flask import Blueprint, flash, jsonify, redirect, render_template, request

from .db import get_db
from .i18n import _
from .security import rate_limit, honeypot_tripped, bot_log
from .services import cart as cartsvc
from .services import catalog
from .services import settings as st
from .util import EMAIL_RE, lek, now_iso

bp = Blueprint("api", __name__)


def _is_fetch():
    return request.headers.get("X-Requested-With") == "fetch" or request.is_json


def _data():
    return request.get_json(silent=True) or request.form


def _safe_next(default="/shporta"):
    nxt = _data().get("next") or request.referrer or default
    u = urlparse(nxt)
    if u.scheme or u.netloc or not nxt.startswith("/") or nxt.startswith("//"):
        return default
    return nxt


def _cart_state():
    lines = cartsvc.lines()
    t = cartsvc.cart_totals(lines)
    s = st.all_settings()
    fee, free_over = st.int_setting("fee", 0, s), st.int_setting("freeOver", 0, s)
    return {
        "count": sum(q for _, q, _ in lines),
        "lines": [{"id": p["id"], "qty": q, "max": m, "line_total": lek(p["price"] * q)} for p, q, m in lines],
        "totals": {"items": t["items"], "sub": lek(t["sub"]), "fee": lek(t["fee"]) if t["fee"] else _("Falas"),
                   "total": lek(t["total"]), "raw_total": t["total"]},
        "freebar": render_template("partials/freebar.html", t=t, free_over=free_over),
        "summary": render_template("partials/cart_summary.html", lines=lines, t=t, fee=fee, free_over=free_over),
        "empty": not lines,
    }


@bp.post("/shporta/shto")
def cart_add():
    d = _data()
    try:
        pid = int(d.get("product") or d.get("id"))
        qty = max(1, min(99, int(d.get("qty") or 1)))
    except (TypeError, ValueError):
        return _err("invalid", _("Kërkesë e pavlefshme."))
    try:
        r = cartsvc.add(pid, qty)
    except cartsvc.CartError as e:
        return _err(e.code, _(e.msg))
    note = _("Maksimumi për këtë produkt: %(n)s copë.", n=r["max"]) if r["capped"] else ""
    if _is_fetch():
        return jsonify(ok=True, count=cartsvc.count(), qty=r["qty"], capped=r["capped"], note=note)
    flash(_("U shtua në shportë") + (" · " + note if note else ""), "success")
    return redirect(_safe_next())


@bp.post("/shporta/sasia")
def cart_qty():
    d = _data()
    try:
        pid, qty = int(d.get("product") or d.get("id")), int(d.get("qty"))
    except (TypeError, ValueError):
        return _err("invalid", _("Kërkesë e pavlefshme."))
    try:
        q = cartsvc.set_qty(pid, max(0, min(qty, 999)))
    except cartsvc.CartError as e:
        return _err(e.code, _(e.msg))
    if _is_fetch():
        return jsonify(ok=True, qty=q, **_cart_state())
    return redirect("/shporta")


@bp.post("/shporta/hiq")
def cart_remove():
    d = _data()
    try:
        pid = int(d.get("product") or d.get("id"))
    except (TypeError, ValueError):
        return _err("invalid", _("Kërkesë e pavlefshme."))
    cartsvc.remove(pid)
    if _is_fetch():
        return jsonify(ok=True, **_cart_state())
    flash(_("Produkti u hoq nga shporta."), "info")
    return redirect("/shporta")


@bp.post("/shporta/pastro")
def cart_clear():
    cartsvc.clear()
    if _is_fetch():
        return jsonify(ok=True, count=0)
    flash(_("Shporta u pastrua."), "info")
    return redirect("/shporta")


def _err(code, msg, status=400):
    if _is_fetch():
        return jsonify(ok=False, error=code, message=msg), status
    flash(msg, "error")
    return redirect(_safe_next())


@bp.get("/api/kerko")
def search_api():
    q = (request.args.get("q") or "").strip()[:80]
    if len(q) < 2:
        return jsonify(q=q, products=[], categories=[], total=0)
    rate_limit("search", 120, 60)
    r = catalog.suggestions(q)
    return jsonify(q=q, total=r["total"], categories=r["categories"],
                   products=[{"id": p["id"], "name": p["name"], "pack": p["pack"], "cat": p["cat_name"], "price": lek(p["price"]),
                              "image": p["image"], "url": "/produkt/%d" % p["id"]} for p in r["products"]])


@bp.post("/abonohu")
def subscribe():
    rate_limit("newsletter", 10, 600)
    d = _data()
    if honeypot_tripped(d):
        bot_log("newsletter")   # answer like a success so the script learns nothing; nothing is stored
        return (jsonify(ok=True), 200) if _is_fetch() else redirect(_safe_next("/") + "#newsletter")
    email = (d.get("email") or "").strip().lower()[:254]
    source = d.get("source") if d.get("source") in ("ballina", "arka", "ofertat") else "ballina"
    if not EMAIL_RE.match(email):
        res = ("invalid", 400)
    else:
        con = get_db()
        row = con.execute("SELECT id, active FROM subscribers WHERE email = ?", (email,)).fetchone()
        if row and row["active"]:
            res = ("duplicate", 200)
        elif row:
            con.execute("UPDATE subscribers SET active=1, unsubscribed_at=NULL, created_at=?, source=? WHERE id=?", (now_iso(), source, row["id"]))
            res = ("ok", 200)
        else:
            con.execute("INSERT INTO subscribers(email, created_at, source, active, token) VALUES (?,?,?,1,?)",
                        (email, now_iso(), source, secrets.token_urlsafe(24)))
            res = ("ok", 200)
    if _is_fetch():
        return (jsonify(ok=True) if res[0] == "ok" else jsonify(error=res[0])), res[1]
    flash({"ok": _("Faleminderit! U abonuat me sukses."), "duplicate": _("Ky email është tashmë i abonuar — nuk ka nevojë të bëni asgjë."),
           "invalid": _("Shkruani një adresë email të vlefshme, p.sh. emri@gmail.com")}[res[0]], "error" if res[0] == "invalid" else "success")
    return redirect(_safe_next("/") + "#newsletter")


@bp.route("/cabonohu/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    con = get_db()
    row = con.execute("SELECT * FROM subscribers WHERE token = ?", (token,)).fetchone()
    done = False
    if row and request.method == "POST":
        con.execute("UPDATE subscribers SET active=0, unsubscribed_at=? WHERE id=?", (now_iso(), row["id"]))
        done = True
    return render_template("pages/cabonohu.html", row=row, done=done or (row is not None and not row["active"]), noindex=True,
                           token=token), (200 if row else 404)
