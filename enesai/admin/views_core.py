"""Admin: login/logout, password, dashboard, operators & permissions, settings, audit log."""
import csv
import io
import json
import re
from datetime import timedelta
from urllib.parse import urlparse

from flask import Response, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from ..db import get_db, transaction
from ..security import client_ip, rate_limit
from ..services import audit, auth, images
from ..services import settings as st
from ..services.catalog import media_url
from ..services.charts import line_chart
from ..util import csv_safe, e164_digits, fmt_date, lek, now, now_iso, valid_phone
from . import bp


def page(tpl, active, title, crumbs, **kw):
    return render_template(tpl, active=active, title=title, crumbs=crumbs, **kw)


# ---------------- auth ----------------

@bp.route("/login", methods=["GET", "POST"])
def login():
    if auth.current_operator():
        return redirect(url_for("admin.dashboard"))
    err, username = None, ""
    nxt = request.values.get("next") or ""
    if request.method == "POST":
        rate_limit("login", 30, 600)
        username = (request.form.get("username") or "").strip()
        row, err = auth.attempt(username, request.form.get("password") or "", client_ip(), request.user_agent.string)
        if row:
            return redirect(_safe_next(nxt))
    status = 429 if err == "locked" else (401 if err else 200)
    return render_template("admin/login.html", error=err, username=username, next=nxt, expired=bool(request.args.get("skadoi")),
                           no_owner=not auth.owner_exists()), status


def _safe_next(nxt):
    u = urlparse(nxt or "")
    return nxt if nxt and nxt.startswith(current_app.config["ADMIN_PATH"]) and not u.netloc and not u.scheme else url_for("admin.dashboard")


@bp.post("/dil")
def logout():
    op = auth.current_operator()
    if op:
        audit.log("Dalje nga paneli", "—", area="auth")
    auth.logout()
    return redirect(url_for("admin.login"))


@bp.route("/fjalekalimi", methods=["GET", "POST"])
@auth.login_required
def change_password():
    err = None
    if request.method == "POST":
        err = auth.change_password(g.operator, request.form.get("current"), request.form.get("new"), request.form.get("confirm"))
        if not err:
            flash("Fjalëkalimi u ndryshua. Sesionet e tjera u mbyllën.", "success")
            return redirect(url_for("admin.dashboard"))
    return page("admin/password.html", "settings", "Fjalëkalimi", "Paneli › Llogaria", error=err)


# ---------------- dashboard ----------------

@bp.get("/")
@auth.login_required
def dashboard():
    con = get_db()
    today = now().date()
    d0 = today.isoformat()
    def day_sum(d):
        r = con.execute("SELECT COUNT(*), COALESCE(SUM(total),0) FROM orders WHERE status<>'cancel' AND substr(created_at,1,10)=?", (d,)).fetchone()
        return r[0], r[1]
    n_today, s_today = day_sum(d0)
    last_week = (today - timedelta(days=7)).isoformat()
    n_lw, s_lw = day_sum(last_week)
    waiting = con.execute("SELECT COUNT(*) FROM orders WHERE status='new'").fetchone()[0]
    low = con.execute("SELECT COUNT(*) FROM products WHERE visible=1 AND stock <= low_threshold").fetchone()[0]
    days = [(today - timedelta(days=13 - i)) for i in range(14)]
    series, prev = [], []
    rows = {r[0]: r[1] for r in con.execute("SELECT substr(created_at,1,10) d, SUM(total) FROM orders WHERE status<>'cancel' AND created_at >= ? GROUP BY d",
                                             ((today - timedelta(days=27)).isoformat(),))}
    for d in days:
        series.append(rows.get(d.isoformat(), 0))
        prev.append(rows.get((d - timedelta(days=14)).isoformat(), 0))
    labels = [d.strftime("%d.%m") if i % 2 == 0 or i == 13 else "" for i, d in enumerate(days)]
    tot, ptot = sum(series), sum(prev)
    chart = line_chart(series, prev, labels, label="Shitjet ditore në lek")
    lows = con.execute("""SELECT p.id, p.name_sq, p.sku, p.stock, (SELECT path FROM product_images i WHERE i.product_id=p.id ORDER BY sort LIMIT 1) img
                          FROM products p WHERE p.visible=1 AND p.stock <= p.low_threshold ORDER BY p.stock, p.name_sq LIMIT 5""").fetchall()
    recent = con.execute("SELECT * FROM orders ORDER BY created_at DESC, id DESC LIMIT 5").fetchall() if auth.can("orders") else []
    activity = con.execute("SELECT * FROM audit_log WHERE operator_id IS NOT NULL AND action NOT IN ('Hyrje në panel','Dalje nga paneli') ORDER BY id DESC LIMIT 4").fetchall()
    imported = con.execute("""SELECT p.id, p.name_sq, p.sku, p.sale_price, p.created_at, (SELECT path FROM product_images i WHERE i.product_id=p.id ORDER BY sort LIMIT 1) img
                              FROM products p ORDER BY p.created_at DESC, p.id DESC LIMIT 3""").fetchall()
    last_job = con.execute("SELECT * FROM import_jobs WHERE status='done' ORDER BY id DESC LIMIT 1").fetchone()
    hour = now().hour
    greet = "Mirëmëngjes" if hour < 12 else ("Mirëdita" if hour < 18 else "Mirëmbrëma")
    weekday = ["E hënë", "E martë", "E mërkurë", "E enjte", "E premte", "E shtunë", "E diel"][today.weekday()]
    return page("admin/dashboard.html", "dash", "Dashboard", "Paneli", greet=greet, today_label="%s, %s" % (weekday, fmt_date(d0)),
                n_today=n_today, s_today=s_today, n_lw=n_lw, s_lw=s_lw, waiting=waiting, low=low, chart=chart, tot=tot, ptot=ptot,
                lows=lows, recent=recent, activity=activity, imported=imported, last_job=last_job,
                avg=(s_today // n_today) if n_today else 0, has_demo=bool(con.execute("SELECT 1 FROM products WHERE is_demo=1 LIMIT 1").fetchone()))


# ---------------- operators ----------------

USERNAME_RE = re.compile(r"^[a-z0-9._]{3,40}$")


def _operators():
    con = get_db()
    ops = []
    for r in con.execute("SELECT * FROM operators ORDER BY (role='owner') DESC, (role='manager') DESC, name"):
        perms = {x[0] for x in con.execute("SELECT section FROM operator_permissions WHERE operator_id=?", (r["id"],))}
        ops.append({"row": r, "perms": perms, "ini": "".join(w[0] for w in r["name"].split()[:2]).upper()})
    return ops


@bp.get("/operatoret")
@auth.requires("operators")
def operators():
    edit = request.args.get("ndrysho", type=int)
    ops = _operators()
    target = next((o for o in ops if o["row"]["id"] == edit), None) if edit else None
    return page("admin/operators.html", "ops", "Operatorët", "Paneli › Menaxhimi", ops=ops, sections=auth.SECTIONS,
                edit=target, open_modal=bool(request.args.get("shto") or target), form={}, errors={})


def _operator_form():
    f = request.form
    data = {"name": (f.get("name") or "").strip()[:80], "username": (f.get("username") or "").strip().lower()[:40],
            "password": f.get("password") or "", "role": f.get("role") if f.get("role") in ("operator", "manager") else "operator",
            "active": f.get("active") == "1", "perms": [s for s in f.getlist("perms") if s in auth.SECTION_KEYS]}
    if data["role"] == "operator" and "coupons" in data["perms"]:
        data["perms"].remove("coupons")  # CR-17: operators can never get Kuponat
    return data


@bp.post("/operatoret")
@auth.requires("operators")
def operator_save():
    con = get_db()
    data = _operator_form()
    oid = request.form.get("id", type=int)
    errors = {}
    if len(data["name"]) < 2:
        errors["name"] = "Shkruani emrin e plotë."
    if not USERNAME_RE.match(data["username"]):
        errors["username"] = "Vetëm shkronja të vogla, pikë, _ ose numra (3–40)."
    elif con.execute("SELECT 1 FROM operators WHERE username=? AND id<>?", (data["username"], oid or 0)).fetchone():
        errors["username"] = "Ky emër përdoruesi ekziston."
    if not oid or data["password"]:
        prob = auth.password_problem(data["password"], data["username"])
        if prob:
            errors["password"] = prob
    target = con.execute("SELECT * FROM operators WHERE id=?", (oid,)).fetchone() if oid else None
    if oid and (not target or target["role"] == "owner"):
        abort(403)  # owner is immutable here
    if errors:
        return page("admin/operators.html", "ops", "Operatorët", "Paneli › Menaxhimi", ops=_operators(), sections=auth.SECTIONS,
                    edit={"row": target, "perms": set(data["perms"])} if target else None, open_modal=True, form=data, errors=errors), 422
    with transaction(con):
        if target:
            con.execute("UPDATE operators SET name=?, username=?, role=?, active=? WHERE id=?",
                        (data["name"], data["username"], data["role"], 1 if data["active"] else 0, oid))
            if data["password"]:
                con.execute("UPDATE operators SET password_hash=?, must_change_password=1 WHERE id=?", (auth.hash_password(data["password"]), oid))
                con.execute("DELETE FROM admin_sessions WHERE operator_id=?", (oid,))
            if not data["active"]:
                con.execute("DELETE FROM admin_sessions WHERE operator_id=?", (oid,))
            action = "Ndryshoi operator"
        else:
            cur = con.execute("INSERT INTO operators(name, username, password_hash, role, active, must_change_password, created_at) VALUES (?,?,?,?,?,1,?)",
                              (data["name"], data["username"], auth.hash_password(data["password"]), data["role"], 1 if data["active"] else 0, now_iso()))
            oid = cur.lastrowid
            action = "Krijoi operator"
        con.execute("DELETE FROM operator_permissions WHERE operator_id=?", (oid,))
        for s in data["perms"]:
            con.execute("INSERT INTO operator_permissions(operator_id, section) VALUES (?,?)", (oid, s))
        audit.log(action, "%s (@%s) · %s" % (data["name"], data["username"], auth.ROLE_LABEL[data["role"]]),
                  after=", ".join(data["perms"]) or "—", area="operators", tone="new", con=con)
    flash("Operatori u ruajt.", "success")
    return redirect(url_for("admin.operators"))


@bp.post("/operatoret/<int:oid>/aktiv")
@auth.requires("operators")
def operator_toggle(oid):
    con = get_db()
    r = con.execute("SELECT * FROM operators WHERE id=?", (oid,)).fetchone()
    if not r or r["role"] == "owner":
        abort(403)
    active = 0 if r["active"] else 1
    with transaction(con):
        con.execute("UPDATE operators SET active=? WHERE id=?", (active, oid))
        if not active:
            con.execute("DELETE FROM admin_sessions WHERE operator_id=?", (oid,))
        audit.log("Aktivizoi operator" if active else "Çaktivizoi operator", "%s (@%s)" % (r["name"], r["username"]), area="operators",
                  tone="success" if active else "danger", con=con)
    return _back("Operatori u %s." % ("aktivizua" if active else "çaktivizua"))


@bp.post("/operatoret/<int:oid>/fshi")
@auth.requires("operators")
def operator_delete(oid):
    con = get_db()
    r = con.execute("SELECT * FROM operators WHERE id=?", (oid,)).fetchone()
    if not r or r["role"] == "owner":
        abort(403)  # the owner can never be deleted or disabled
    with transaction(con):
        con.execute("DELETE FROM operators WHERE id=?", (oid,))
        audit.log("Fshiu operator", "%s (@%s)" % (r["name"], r["username"]), area="operators", tone="danger", con=con)
    return _back("Operatori u fshi.")


@bp.post("/operatoret/lejet")
@auth.requires("operators")
def operator_matrix():
    con = get_db()
    with transaction(con):
        for r in con.execute("SELECT * FROM operators WHERE role<>'owner'").fetchall():
            perms = [s for s in auth.SECTION_KEYS if request.form.get("p-%d-%s" % (r["id"], s)) == "1"]
            if r["role"] == "operator" and "coupons" in perms:
                perms.remove("coupons")
            before = {x[0] for x in con.execute("SELECT section FROM operator_permissions WHERE operator_id=?", (r["id"],))}
            if set(perms) != before:
                con.execute("DELETE FROM operator_permissions WHERE operator_id=?", (r["id"],))
                for s in perms:
                    con.execute("INSERT INTO operator_permissions(operator_id, section) VALUES (?,?)", (r["id"], s))
                audit.log("Ndryshoi lejet", "%s (@%s)" % (r["name"], r["username"]), ", ".join(sorted(before)) or "—", ", ".join(perms) or "—",
                          area="operators", tone="info", con=con)
    return _back("Lejet u ruajtën.")


def _back(msg, tone="success"):
    if request.headers.get("X-Requested-With") == "fetch":
        return {"ok": True, "message": msg}
    flash(msg, tone)
    ref = request.referrer or ""
    return redirect(ref if urlparse(ref).netloc in ("", request.host) and ref else url_for("admin.dashboard"))


# ---------------- settings ----------------

SETTING_FIELDS = ["tradeName", "short", "legalName", "nipt", "whatsapp", "waMode", "prefix", "web", "note", "phone", "email", "address",
                  "hours", "store_lat", "store_lng", "maps_link", "fee", "freeOver", "delivery_area", "zones", "session_timeout",
                  "offers_until", "facebook", "instagram", "tiktok", "studio_call", "studio_wa"]


def _validate_settings(f):
    v = {k: (f.get(k) or "").strip() for k in SETTING_FIELDS if k in f}
    err = {}
    if v.get("nipt") and not re.match(r"^[A-Z]\d{8}[A-Z]$", v["nipt"].upper()):
        err["nipt"] = "NIPT: shkronjë · 8 shifra · shkronjë (p.sh. L01234567A)."
    elif v.get("nipt"):
        v["nipt"] = v["nipt"].upper()
    for k in ("whatsapp", "phone"):
        if v.get(k) and not valid_phone(v[k]):
            err[k] = "Numri nuk duket i saktë. Shkruajeni me +355."
    if v.get("email") and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$", v["email"]):
        err["email"] = "Email-i nuk duket i saktë."
    for k in ("fee", "freeOver"):
        if k in v:
            s = v[k].replace(".", "").replace(" ", "")
            if not s.isdigit() or int(s) > 1_000_000:
                err[k] = "Shkruani një numër të plotë në lek."
            else:
                v[k] = str(int(s))
    if "prefix" in v:
        p = re.sub(r"[^A-Z]", "", v["prefix"].upper())[:4]
        if not p:
            err["prefix"] = "Vetëm shkronja A–Z (1–4)."
        v["prefix"] = p
    for k, lo, hi in (("store_lat", -90, 90), ("store_lng", -180, 180)):
        if v.get(k):
            try:
                x = float(v[k].replace(",", "."))
                assert lo <= x <= hi
                v[k] = "%.6f" % x
            except (ValueError, AssertionError):
                err[k] = "Koordinatë e pavlefshme."
    for k in ("maps_link", "facebook", "instagram", "tiktok"):
        if v.get(k) and not v[k].startswith("https://"):
            err[k] = "Lidhja duhet të fillojë me https://"
    if v.get("waMode") not in (None, "api", "manual"):
        v["waMode"] = "manual"
    if v.get("session_timeout") and v["session_timeout"] not in st.SESSION_TIMEOUTS:
        v["session_timeout"] = "30"
    if v.get("offers_until") and not re.match(r"^\d{4}-\d{2}-\d{2}$", v["offers_until"]):
        err["offers_until"] = "Data nuk është e vlefshme."
    # hours table
    hours = []
    for i in range(7):
        o, c, closed = (f.get("h-open-%d" % i) or "").strip(), (f.get("h-close-%d" % i) or "").strip(), f.get("h-closed-%d" % i) == "1"
        for t in (o, c):
            if t and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t):
                err["hours_json"] = "Orari: përdorni formatin HH:MM."
        hours.append({"open": o, "close": c, "closed": closed})
    if any(h["open"] or h["close"] or h["closed"] for h in hours):
        v["hours_json"] = json.dumps(hours)
    return v, err


@bp.route("/cilesimet", methods=["GET", "POST"])
@auth.requires("settings")
def settings():
    s = dict(st.all_settings())
    errors = {}
    if request.method == "POST":
        v, errors = _validate_settings(request.form)
        for kind in ("logo_dark", "logo_light"):
            fobj = request.files.get(kind)
            if fobj and fobj.filename:
                try:
                    v[kind] = images.save_logo(fobj, kind)
                except images.ImageError as e:
                    errors[kind] = str(e)
        if v.get("waMode") == "api" and not _wa_api_ready():
            errors["waMode"] = "Mënyra automatike kërkon kredencialet e WhatsApp Business API në .env (WA_TOKEN, WA_PHONE_ID, WA_TEMPLATE)."
        if not errors:
            con = get_db()
            changed = [k for k in v if str(s.get(k, "")) != str(v[k])]
            with transaction(con):
                st.save(v, con)
                if changed:
                    audit.log("Ndryshoi cilësimet", ", ".join(changed)[:380], area="settings", tone="info", con=con)
            flash("Cilësimet u ruajtën — Faturat e reja përdorin të dhënat e reja.", "success")
            return redirect(url_for("admin.settings"))
        s.update(v)
    return page("admin/settings.html", "settings", "Cilësimet", "Paneli › Sistemi", s=s, errors=errors, hours=st.hours_table(s),
                missing=st.missing_invoice_fields(s), timeouts=st.SESSION_TIMEOUTS, wa_api_ready=_wa_api_ready(),
                next_nr="%s-%d-%05d" % (s.get("prefix") or "EA", now().year, (get_db().execute(
                    "SELECT last FROM order_counters WHERE prefix=? AND year=?", (s.get("prefix") or "EA", now().year)).fetchone() or [0])[0] + 1),
                admin_path=current_app.config["ADMIN_PATH"])


def _wa_api_ready():
    c = current_app.config
    return bool(c.get("WA_TOKEN") and c.get("WA_PHONE_ID") and c.get("WA_TEMPLATE"))


@bp.post("/cilesimet/sesionet")
@auth.login_required
def end_sessions():
    auth.end_other_sessions(g.operator)
    audit.log("Mbylli sesionet e tjera", "@" + g.operator["username"], area="auth")
    return _back("Sesionet e tjera u mbyllën.")


@bp.get("/cilesimet/fature-shembull.pdf")
@auth.requires("settings")
def sample_invoice():
    """Preview of the invoice with the CURRENT settings and fictitious data (never stored)."""
    import tempfile
    from flask import send_file
    from ..services import invoice_pdf
    s = st.all_settings()
    order = {"nr": "%s-%d-00000" % (s.get("prefix") or "EA", now().year), "created_at": now_iso(), "name": "Emri", "surname": "Mbiemri",
             "phone": "069 000 0000", "email": "", "address": "Rruga, Pallati, Ap.", "zone": "", "city": s.get("city") or "Vlorë",
             "courier_note": "", "lat": 40.466, "lng": 19.4914, "loc_source": "map", "accuracy_m": None, "items_count": 2, "subtotal": 600,
             "discount": 60, "coupon_code": "SHEMBULL", "coupon_pct": 10, "delivery": st.int_setting("fee", 0, s), "total": 540 + st.int_setting("fee", 0, s)}
    items = [{"name": "Produkt shembull", "pack": "1 kg", "sku": "SKU-0001", "qty": 2, "unit_price": 300}]
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    invoice_pdf.build(order, items, st.seller_snapshot(s), tmp.name)
    return send_file(tmp.name, mimetype="application/pdf", download_name="Fatura-shembull.pdf", max_age=0)


# ---------------- audit log (read-only) ----------------

TONES = {"Hyrje në panel": "neutral"}


@bp.get("/regjistri")
@auth.requires("audit")
def audit_page():
    con = get_db()
    where, args = [], []
    opf, area, d1, d2 = request.args.get("op", ""), request.args.get("lloji", ""), request.args.get("nga", ""), request.args.get("deri", "")
    if opf == "system":
        where.append("operator_id IS NULL")
    elif opf.isdigit():
        where.append("operator_id = ?"); args.append(int(opf))
    if area:
        where.append("area = ?"); args.append(area)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d1):
        where.append("at >= ?"); args.append(d1)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d2):
        where.append("at < ?"); args.append(d2 + "T99")
    sw = (" WHERE " + " AND ".join(where)) if where else ""
    if request.args.get("eksporto") == "csv":
        rows = con.execute("SELECT * FROM audit_log" + sw + " ORDER BY id DESC LIMIT 50000", args).fetchall()
        return _csv("regjistri.csv", ["Koha", "Operatori", "Veprimi", "Objekti", "Para", "Pas", "IP"],
                    [[r["at"].replace("T", " "), r["operator_name"], r["action"], r["object"], r["before"], r["after"], r["ip"]] for r in rows])
    total = con.execute("SELECT COUNT(*) FROM audit_log" + sw, args).fetchone()[0]
    per = 50
    pages = max(1, -(-total // per))
    pg = min(max(1, request.args.get("faqe", 1, type=int)), pages)
    rows = con.execute("SELECT * FROM audit_log" + sw + " ORDER BY id DESC LIMIT ? OFFSET ?", args + [per, (pg - 1) * per]).fetchall()
    ops = con.execute("SELECT id, name FROM operators ORDER BY name").fetchall()

    def page_url(n):
        a = request.args.to_dict(); a["faqe"] = n
        return url_for("admin.audit_page", **a)
    return page("admin/audit.html", "audit", "Regjistri i Veprimeve", "Paneli › Sistemi", rows=rows, total=total, pg=pg, pages=pages,
                page_url=page_url, ops=ops, f={"op": opf, "lloji": area, "nga": d1, "deri": d2}, per=per)


def _csv(name, header, rows):
    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM so Excel shows ë/ç correctly
    w = csv.writer(buf, delimiter=";")
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(x) for x in r])
    audit.log("Eksportoi CSV", name, area="export")
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=%s" % name})
