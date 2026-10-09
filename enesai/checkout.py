"""Checkout (/arka), coupon check API and order confirmation (/porosia/<nr>)."""
import json
import secrets

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, session)

from .i18n import _
from .security import rate_limit
from .services import cart as cartsvc
from .services import coupons, orders
from .services import settings as st
from .services.catalog import media_url
from .services.totals import totals
from .util import maps_url, wa_url

bp = Blueprint("checkout", __name__)
VLORE = (40.4660, 19.4914)


def _idem():
    k = session.get("idem")
    if not k:
        k = secrets.token_urlsafe(24)
        session["idem"] = k
    return k


def _center():
    s = st.all_settings()
    try:
        return (float(s["store_lat"]), float(s["store_lng"])) if s.get("store_lat") and s.get("store_lng") else VLORE
    except ValueError:
        return VLORE


def _ctx(lines, coupon=None, coupon_state=None, v=None, loc=None, fe=None, submitted=False, form_alert=None):
    s = st.all_settings()
    fee, free_over = st.int_setting("fee", 0, s), st.int_setting("freeOver", 0, s)
    t = totals([(p["price"], q) for p, q, _m in lines], coupon["pct"] if coupon else 0, fee, free_over)
    fe = fe or {}
    errors = [(k, _(orders.LABELS[k]), _(m).rstrip(".")) for k, m in fe.items() if k in orders.LABELS]
    loc_state = {"state": "ok", **loc} if loc else {"state": "idle", "error": "co-loc" in fe}
    return dict(lines=lines, t=t, fee=fee, free_over=free_over, coupon=coupon,
                coupon_state=coupon_state if coupon_state is not None else ({"applied": coupon} if coupon else {}),
                v=v or {"zone": ""}, loc=loc_state, fe=fe, errors=errors, submitted=submitted, form_alert=form_alert,
                zone_options=[(z, z) for z in st.zones()], map_center=_center(), idem=_idem(), active="shop", noindex=True)


def _coupon_from(code):
    if not code:
        return None, {}
    try:
        c = coupons.check(code)
        return c, {"applied": c}
    except coupons.CouponError as e:
        return None, {"error": e.code, "value": coupons.normalize(code), "used_on": e.used_on}


@bp.route("/arka", methods=["GET", "POST"])
def checkout():
    lines = cartsvc.lines()
    if not lines:
        if request.method == "POST":
            flash(_("Shporta juaj është bosh."), "info")
        return redirect("/shporta")
    if request.method == "GET":
        return render_template("pages/arka.html", **_ctx(lines))

    form = request.form
    action = form.get("action") or "order"
    code = form.get("coupon_input") if action == "coupon" else form.get("coupon")
    v, loc, fe = orders.validate(form)
    if action == "coupon":  # no-JS “Apliko”
        rate_limit("coupon", 20, 600)
        c, cs = _coupon_from(code or "")
        if not code:
            cs = {"error": "empty"}
        return render_template("pages/arka.html", **_ctx(lines, c, cs, v, loc))
    if action == "coupon-remove":
        return render_template("pages/arka.html", **_ctx(lines, None, {}, v, loc))

    rate_limit("order", 12, 600)
    coupon, cstate = _coupon_from(code)
    if code and not coupon:
        cstate = {"error": "gone" if cstate.get("error") in ("used", "cancelled", "expired") else cstate.get("error"), "value": coupons.normalize(code)}
        return render_template("pages/arka.html", **_ctx(lines, None, cstate, v, loc, fe, True,
                                                         {"title": _("Kuponi nuk vlen më"), "text": " " + _("Totali u rillogarit pa kupon. Kontrolloni dhe konfirmoni sërish.")})), 409
    if fe:
        return render_template("pages/arka.html", **_ctx(lines, coupon, cstate, v, loc, fe, True)), 422
    try:
        order, token = orders.create_order(v, loc, [(p["id"], q) for p, q, _m in lines], coupon["code"] if coupon else None, form.get("idem") or "")
    except coupons.CouponError as e:
        return render_template("pages/arka.html", **_ctx(lines, None, {"error": "gone", "value": coupons.normalize(code)}, v, loc, {}, True,
                                                         {"title": _("Kuponi nuk vlen më"), "text": " " + _("Ky kod u përdor ose u anulua ndërkohë. Totali u rillogarit pa kupon.")})), 409
    except orders.OrderError as e:
        if e.code == "cart_changed":
            names = ", ".join(n for _k, n in (e.detail or []))
            flash(_("Disa produkte ndryshuan ndërkohë (stoku ose disponueshmëria): %(n)s. Kontrolloni shportën.", n=names), "error")
            return redirect("/shporta")
        if e.code == "idem":
            session.pop("idem", None)
            flash(_("Formulari skadoi. Provoni sërish."), "error")
            return redirect("/arka")
        raise
    if token is None:  # repeated submit of an order that already exists (idempotency)
        token = session.get("orders", {}).get(order["nr"])
        if not token:
            abort(409)
    cartsvc.clear()
    session.pop("idem", None)
    keep = dict(list(session.get("orders", {}).items())[-4:])
    keep[order["nr"]] = token
    session["orders"] = keep
    if st.get("waMode") == "api" and orders.wa_api_configured():
        from .services import whatsapp
        whatsapp.queue_send(order["id"])
    return redirect("/porosia/%s?t=%s" % (order["nr"], token))


@bp.post("/api/kupon/kontrollo")
def coupon_check():
    rate_limit("coupon", 20, 600)
    d = request.get_json(silent=True) or request.form
    code = d.get("code") or ""
    lines = cartsvc.lines()
    if not code.strip():
        c, cs = None, {"error": "empty"}
    elif d.get("remove") == "1":
        c, cs = None, {}
    else:
        c, cs = _coupon_from(code)
    ctx = _ctx(lines, c, cs)
    from flask import render_template_string
    final = render_template_string('{% from "macros/checkout.html" import checkout_final with context %}{{ checkout_final(t, coupon, coupon_state, terms_checked) }}',
                                   terms_checked=d.get("terms") in ("1", True, "true"), **ctx)
    summary = render_template_string('{% from "macros/checkout.html" import checkout_summary with context %}{{ checkout_summary(lines, t, coupon, fee, free_over) }}', **ctx)
    resp = {"final": final, "summary": summary}
    if c:
        resp.update(ok=True, code=c["code"], pct=c["pct"])
    else:
        resp.update(ok=False, error=cs.get("error"))
    return jsonify(resp)


# ---------------- confirmation ----------------

def _authorized_order(nr):
    o = orders.get(nr)
    token = request.args.get("t") or (request.get_json(silent=True) or {}).get("t") or request.form.get("t")
    if not o or not orders.token_ok(o, token):
        abort(404)  # do not reveal whether the number exists
    return o, token


def _order_view(o):
    its = orders.items(o)
    snap = json.loads(o["seller_snapshot"])
    return its, snap


@bp.get("/porosia/<nr>")
def confirmation(nr):
    o, token = _authorized_order(nr)
    its, snap = _order_view(o)
    auto = bool(o["wa_sent_at"])  # only a verified API send shows the “automatic” panel
    text = orders.order_text(o, its)
    num = orders.market_wa_digits(o)
    return render_template("pages/porosia.html", o=o, its=its, snap=snap, token=token, auto=auto,
                           wa_link=wa_url(num, text), wa_has_number=bool(num), maps=maps_url(o["lat"], o["lng"]),
                           pdf_url="/porosia/%s/fatura.pdf?t=%s" % (o["nr"], token), STATUS=orders.STATUS, active="shop",
                           noindex=True, cart_count_override=0)


@bp.get("/porosia/<nr>/fatura.pdf")
def confirmation_pdf(nr):
    o, _t = _authorized_order(nr)
    from .services import invoice_pdf
    path = invoice_pdf.ensure_pdf(o)
    return send_file(path, mimetype="application/pdf", as_attachment=request.args.get("print") != "1",
                     download_name="Fatura-%s.pdf" % o["nr"], max_age=0)


@bp.post("/porosia/<nr>/wa")
def confirmation_wa(nr):
    o, _t = _authorized_order(nr)
    orders.mark_wa_opened(o["nr"])
    return ("", 204)
