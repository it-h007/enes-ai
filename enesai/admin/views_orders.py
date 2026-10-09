"""Admin: Porositë (status flow + drawer), Faturat (search + PDF/print), Kuponat (Owner/Manager)."""
import json
from datetime import timedelta

from flask import abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from ..db import get_db, transaction
from ..services import audit, auth, coupons, invoice_pdf
from ..services import orders as osvc
from ..services import settings as st
from ..util import fmt_date, maps_url, now, wa_url
from . import bp
from .views_core import _csv, page

TABS = [("Të gjitha", ""), ("E re", "new"), ("Në përgatitje", "prep"), ("Në rrugë", "route"), ("Dorëzuar", "done"), ("Anuluar", "cancel")]
PERIODS = [("", "Çdo periudhë"), ("sot", "Sot"), ("7", "7 ditët e fundit"), ("muaj", "Ky muaj")]


def _period(p):
    today = now().date()
    if p == "sot":
        return today.isoformat(), None
    if p == "7":
        return (today - timedelta(days=6)).isoformat(), None
    if p == "muaj":
        return today.replace(day=1).isoformat(), None
    return None, None


def _drawer_ctx(o):
    its = osvc.items(o)
    return {"o": o, "its": its, "maps": maps_url(o["lat"], o["lng"]), "courier": wa_url("", osvc.courier_text(o)), "flow": osvc.FLOW,
            "coupon_back": bool(o["coupon_code"])}


@bp.get("/porosite")
@auth.requires("orders")
def orders():
    con = get_db()
    tab = request.args.get("status", "")
    tab = tab if tab in osvc.STATUS else ""
    q = (request.args.get("q") or "").strip()[:80]
    per = request.args.get("periudha", "")
    zone = request.args.get("zona", "")
    d1, d2 = _period(per)
    if request.args.get("eksporto") == "csv":
        rows, _t = osvc.search(q, tab or None, 100000, 0, date_from=d1, zone=zone or None)
        return _csv("porosite.csv", ["Nr", "Data", "Klienti", "Telefoni", "Email", "Zona", "Adresa", "Artikuj", "Nëntotali", "Kuponi", "Zbritja", "Dërgesa", "Totali", "Statusi"],
                    [[r["nr"], r["created_at"].replace("T", " "), r["name"] + " " + r["surname"], r["phone"], r["email"], r["zone"], r["address"],
                      r["items_count"], r["subtotal"], r["coupon_code"] or "", r["discount"], r["delivery"], r["total"], osvc.STATUS[r["status"]]] for r in rows])
    counts = {"": con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]}
    for r in con.execute("SELECT status, COUNT(*) FROM orders GROUP BY status"):
        counts[r[0]] = r[1]
    pg = max(1, request.args.get("faqe", 1, type=int))
    per_page = 50
    rows, total = osvc.search(q, tab or None, per_page, (pg - 1) * per_page, date_from=d1, zone=zone or None)
    pages = max(1, -(-total // per_page))
    sel = request.args.get("hap")
    drawer = None
    if sel:
        o = osvc.get(sel)
        if o:
            drawer = _drawer_ctx(o)

    def page_url(n):
        a = request.args.to_dict(); a["faqe"] = n; a.pop("hap", None)
        return url_for("admin.orders", **a)
    return page("admin/orders.html", "orders", "Porositë", "Paneli › Menaxhimi", rows=rows, total=total, counts=counts, tabs=TABS, tab=tab, q=q,
                periods=PERIODS, per=per, zone=zone, zones=st.zones(), drawer=drawer, pg=pg, pages=pages, page_url=page_url, sel=sel)


@bp.get("/porosite/<nr>/drawer")
@auth.requires("orders")
def order_drawer(nr):
    o = osvc.get(nr) or abort(404)
    return render_template("admin/_order_drawer.html", dynamic=True, **_drawer_ctx(o))


@bp.post("/porosite/<nr>/statusi")
@auth.requires("orders")
def order_status(nr):
    ns = request.form.get("status")
    try:
        o, returned = osvc.change_status(nr, ns, g.operator)
    except osvc.OrderError as e:
        msg = {"cancelled_final": "Porosia është anuluar — statusi nuk ndryshohet më.", "missing": "Porosia nuk u gjet.",
               "bad_status": "Status i pavlefshëm."}.get(e.code, "Gabim.")
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify(ok=False, message=msg), 409
        flash(msg, "error")
        return redirect(request.referrer or url_for("admin.orders"))
    msg = "%s → %s%s" % (nr, osvc.STATUS[o["status"]], " · kuponi u rikthye" if returned else "")
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, message=msg, drawer=render_template("admin/_order_drawer.html", dynamic=True, **_drawer_ctx(o)))
    flash("Statusi u ndryshua: " + msg, "success")
    return redirect(request.referrer or url_for("admin.orders", hap=nr))


# ---------------- Faturat ----------------

def _can_invoice_pdf():
    return auth.can("invoices") or auth.can("orders")


@bp.get("/faturat")
@auth.requires("invoices")
def invoices():
    q = (request.args.get("q") or "").strip()[:80]
    pg = max(1, request.args.get("faqe", 1, type=int))
    rows, total = osvc.search(q, None, 30, (pg - 1) * 30)
    sel = request.args.get("nr")
    o = osvc.get(sel) if sel else (rows[0] if rows else None)
    detail = None
    if o:
        detail = {"o": o, "its": osvc.items(o), "snap": json.loads(o["seller_snapshot"]), "maps": maps_url(o["lat"], o["lng"]),
                  "courier": wa_url("", osvc.courier_text(o))}
    pages = max(1, -(-total // 30))

    def page_url(n):
        return url_for("admin.invoices", q=q or None, faqe=n)
    con = get_db()
    examples = con.execute("SELECT nr, surname, phone, email FROM orders ORDER BY id DESC LIMIT 1").fetchone()
    return page("admin/invoices.html", "invoices", "Faturat", "Paneli › Menaxhimi", rows=rows, total=total, q=q, detail=detail, pg=pg, pages=pages,
                page_url=page_url, examples=examples)


@bp.get("/faturat/<nr>.pdf")
@auth.login_required
def invoice_file(nr):
    if not _can_invoice_pdf():
        audit.log("Akses i ndaluar", "PDF " + nr, area="invoices", tone="danger")
        abort(403)
    o = osvc.get(nr) or abort(404)
    path = invoice_pdf.ensure_pdf(o)
    audit.log("Hapi faturën PDF", nr, area="invoices")
    return send_file(path, mimetype="application/pdf", as_attachment=request.args.get("print") != "1", download_name="Fatura-%s.pdf" % nr, max_age=0)


# ---------------- Kuponat ----------------

@bp.get("/kuponat")
@auth.login_required
def coupons_page():
    if not auth.can("coupons"):
        # design: operators see the locked panel (no codes are shown); still a 403 for the server log
        audit.log("Akses i ndaluar", "GET " + request.path, area="coupons", tone="danger")
        return page("admin/coupons_locked.html", "coupons", "Kuponat", "Paneli › Marketingu"), 403
    return _coupons_view()


def _coupons_view(created=None, form=None, errors=None, status=200):
    con = get_db()
    flt = request.args.get("status", "")
    q = (request.args.get("q") or "").strip()[:60]
    rows = con.execute("SELECT * FROM coupons ORDER BY created_at DESC").fetchall()
    cnt = {"active": 0, "used": 0, "expired": 0, "cancelled": 0}
    view = []
    from ..util import norm
    nq = norm(q)
    for r in rows:
        stt = coupons.state(r)
        cnt[stt] += 1
        if flt and stt != flt:
            continue
        if nq and nq not in norm(" ".join([r["code"], r["note"] or "", r["used_by"] or "", r["used_order_nr"] or ""])):
            continue
        view.append((r, stt))
    form = form or {"code": coupons.generate(con), "pct": 10, "until": "", "note": ""}
    return page("admin/coupons.html", "coupons", "Kuponat", "Paneli › Marketingu", rows=view, all_n=len(rows), cnt=cnt, flt=flt, q=q,
                created=created, form=form, errors=errors or {}, max_pct=min(90, __import__("flask").current_app.config["COUPON_MAX_PCT"])), status


@bp.post("/kuponat")
@auth.requires("coupons")
def coupon_create():
    f = request.form
    if f.get("action") == "generate":
        form = {"code": coupons.generate(), "pct": f.get("pct", 10), "until": f.get("until", ""), "note": f.get("note", "")}
        return _coupons_view(form=form)
    form = {"code": f.get("code", ""), "pct": f.get("pct", ""), "until": f.get("until", ""), "note": f.get("note", "")}
    con = get_db()
    with transaction(con):
        c, errors = coupons.create(form["code"], form["pct"], form["until"] or None, form["note"], g.operator, con)
    if errors:
        return _coupons_view(form=form, errors=errors, status=422)
    flash("Kuponi u krijua: %s · −%d%% · një përdorim" % (c["code"], c["pct"]), "success")
    return _coupons_view(created=c)


@bp.post("/kuponat/<code>/anulo")
@auth.requires("coupons")
def coupon_cancel(code):
    con = get_db()
    with transaction(con):
        ok = coupons.cancel(code, g.operator, con)
    flash(("Kuponi %s u anulua — nuk pranohet më." % code) if ok else "Vetëm kuponat aktivë mund të anulohen.", "info" if ok else "error")
    return redirect(url_for("admin.coupons_page"))
