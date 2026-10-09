"""Admin: Abonentët, Ofertat e email-it (prepare only — no SMTP sending), Reklamat & Njoftimet, Raportet."""
import json
import re
from datetime import date, timedelta

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for

from ..db import get_db, transaction
from ..services import audit, auth, content, images
from ..services.catalog import list_products, media_url
from ..services.charts import bar_chart
from ..util import EMAIL_RE, fmt_date, lek, now, now_iso
from . import bp
from .views_core import _back, _csv, page

SOURCES = {"ballina": "Ballina", "arka": "Arka", "ofertat": "Ofertat"}


# ---------------- subscribers ----------------

@bp.get("/abonentet")
@auth.requires("subscribers")
def subscribers():
    con = get_db()
    q = (request.args.get("q") or "").strip().lower()[:80]
    flt = request.args.get("statusi", "")
    where, args = [], []
    if q:
        where.append("email LIKE ?"); args.append("%" + q.replace("%", "") + "%")
    if flt in ("1", "0"):
        where.append("active = ?"); args.append(int(flt))
    sw = (" WHERE " + " AND ".join(where)) if where else ""
    if request.args.get("eksporto") == "csv":
        rows = con.execute("SELECT * FROM subscribers" + sw + " ORDER BY created_at DESC", args).fetchall()
        return _csv("abonentet.csv", ["email", "data", "burimi", "statusi", "çabonuar_më"],
                    [[r["email"], r["created_at"].replace("T", " "), SOURCES.get(r["source"], r["source"]), "aktiv" if r["active"] else "çabonuar",
                      (r["unsubscribed_at"] or "").replace("T", " ")] for r in rows])
    active = con.execute("SELECT COUNT(*) FROM subscribers WHERE active=1").fetchone()[0]
    month = now().date().replace(day=1).isoformat()
    new_month = con.execute("SELECT COUNT(*) FROM subscribers WHERE active=1 AND created_at >= ?", (month,)).fetchone()[0]
    unsub = con.execute("SELECT COUNT(*) FROM subscribers WHERE active=0").fetchone()[0]
    top = con.execute("SELECT source, COUNT(*) n FROM subscribers GROUP BY source ORDER BY n DESC LIMIT 1").fetchone()
    total_all = con.execute("SELECT COUNT(*) FROM subscribers").fetchone()[0]
    last_mail = con.execute("SELECT * FROM email_campaigns WHERE status IN ('prepared','sent') ORDER BY COALESCE(sent_at, prepared_at) DESC LIMIT 1").fetchone()
    pg = max(1, request.args.get("faqe", 1, type=int))
    total = con.execute("SELECT COUNT(*) FROM subscribers" + sw, args).fetchone()[0]
    rows = con.execute("SELECT * FROM subscribers" + sw + " ORDER BY created_at DESC LIMIT 50 OFFSET ?", args + [(pg - 1) * 50]).fetchall()
    emails = [r[0] for r in con.execute("SELECT email FROM subscribers WHERE active=1 ORDER BY created_at DESC LIMIT 5000")]
    pages = max(1, -(-total // 50))

    def page_url(n):
        a = request.args.to_dict(); a["faqe"] = n
        return url_for("admin.subscribers", **a)
    return page("admin/subscribers.html", "subs", "Abonentët", "Paneli › Marketingu", rows=rows, n_active=active, new_month=new_month, unsub=unsub,
                top=top, total_all=total_all, last_mail=last_mail, emails=emails, sources=SOURCES, q=q, flt=flt, pg=pg, pages=pages, page_url=page_url, total=total)


@bp.post("/abonentet/<int:sid>/hiq")
@auth.requires("subscribers")
def subscriber_remove(sid):
    con = get_db()
    r = con.execute("SELECT email FROM subscribers WHERE id=?", (sid,)).fetchone() or abort(404)
    with transaction(con):
        con.execute("DELETE FROM subscribers WHERE id=?", (sid,))
        audit.log("Fshiu abonent", r["email"][:2] + "…@" + r["email"].split("@")[-1], area="email", tone="danger", con=con)
    return _back("Abonenti u hoq.")


@bp.post("/abonentet/<int:sid>/cabono")
@auth.requires("subscribers")
def subscriber_unsub(sid):
    con = get_db()
    con.execute("UPDATE subscribers SET active=0, unsubscribed_at=? WHERE id=? AND active=1", (now_iso(), sid))
    audit.log("Çabonoi abonent", "#%d" % sid, area="email", con=con)
    return _back("Abonenti u çabonua.")


# ---------------- e-mail offers ----------------

def _offer_products(ids):
    if not ids:
        return []
    res = list_products({"ids": ids, "sort": "zbritja"}, per_page=12)
    return res["items"]


@bp.route("/email", methods=["GET", "POST"])
@auth.requires("email")
def email_offers():
    con = get_db()
    cid = request.values.get("id", type=int)
    camp = con.execute("SELECT * FROM email_campaigns WHERE id=?", (cid,)).fetchone() if cid else None
    errors = {}
    if request.method == "POST":
        f = request.form
        subject, intro = (f.get("subject") or "").strip()[:120], (f.get("intro") or "").strip()[:1000]
        button = (f.get("button_text") or "Shiko ofertat").strip()[:40]
        ids = [int(x) for x in f.getlist("product_ids") if x.isdigit()][:12]
        if f.get("add_offers") == "1":
            ids = [p["id"] for p in list_products({"sale": True, "offers_page": True, "sort": "zbritja"}, per_page=6)["items"]]
        if len(subject) < 3:
            errors["subject"] = "Shkruani subjektin."
        if not ids and not intro:
            errors["intro"] = "Shtoni një tekst hyrës ose të paktën një produkt."
        action = f.get("action")
        if not errors or f.get("add_offers") == "1":
            t = now_iso()
            with transaction(con):
                if camp and camp["status"] == "draft":
                    con.execute("UPDATE email_campaigns SET subject=?, intro=?, button_text=?, product_ids=? WHERE id=?", (subject, intro, button, json.dumps(ids), camp["id"]))
                    cid = camp["id"]
                else:
                    cid = con.execute("INSERT INTO email_campaigns(subject, intro, button_text, product_ids, status, created_by, created_at) VALUES (?,?,?,?, 'draft', ?, ?)",
                                      (subject or "Ofertat e Javës", intro, button, json.dumps(ids), g.operator["name"], t)).lastrowid
                if action == "prepare" and not errors:
                    n = con.execute("SELECT COUNT(*) FROM subscribers WHERE active=1").fetchone()[0]
                    con.execute("UPDATE email_campaigns SET status='prepared', prepared_at=?, recipients=? WHERE id=?", (t, n, cid))
                    audit.log("Përgatiti email-in", subject, after="%d marrës" % n, area="email", con=con)
                elif action == "sent":
                    con.execute("UPDATE email_campaigns SET status='sent', sent_at=? WHERE id=? AND status='prepared'", (t, cid))
                    audit.log("Shënoi email-in si të dërguar", subject, area="email", con=con)
            flash({"prepare": "Email-i u përgatit. Kopjoni HTML-në dhe listën BCC te shërbimi juaj i email-it.", "sent": "U shënua si i dërguar."}.get(action, "Drafti u ruajt."), "success")
            return redirect(url_for("admin.email_offers", id=cid))
        camp_form = {"subject": subject, "intro": intro, "button_text": button, "product_ids": json.dumps(ids), "status": "draft", "id": cid}
    else:
        camp_form = dict(camp) if camp else {"subject": "Ofertat e Javës në ENES’AI", "intro": "", "button_text": "Shiko ofertat", "product_ids": "[]", "status": "draft", "id": None}
    picks = _offer_products(json.loads(camp_form["product_ids"] or "[]"))
    offers = list_products({"sale": True, "sort": "zbritja"}, per_page=30)["items"]
    history = con.execute("SELECT * FROM email_campaigns ORDER BY id DESC LIMIT 20").fetchall()
    n_active = con.execute("SELECT COUNT(*) FROM subscribers WHERE active=1").fetchone()[0]
    base = current_app.config.get("PUBLIC_BASE_URL") or request.host_url.rstrip("/")
    html = render_template("email/offer.html", c=camp_form, picks=picks, base=base) if camp_form.get("id") else ""
    bcc = ", ".join(r[0] for r in con.execute("SELECT email FROM subscribers WHERE active=1 ORDER BY id")) if camp_form["status"] in ("prepared", "sent") else ""
    return page("admin/email_offers.html", "mail", "Ofertat e Email-it", "Paneli › Marketingu", c=camp_form, picks=picks, offers=offers, history=history,
                n_active=n_active, errors=errors, email_html=html, bcc=bcc, base=base)


# ---------------- announcements / ads / jobs ----------------

TYPE_OPTS = [("njoftim", "Njoftim"), ("reklame", "Reklamë"), ("pune", "Shpallje pune")]


def _parse_dt(v, end=False):
    v = (v or "").strip()
    if not v:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?$", v)
    if not m:
        raise ValueError(v)
    return m.group(1) + "T" + (m.group(2) or ("23:59" if end else "00:00")) + (":59" if end else ":00")


@bp.get("/reklamat")
@auth.requires("ads")
def ads():
    con = get_db()
    rows = con.execute("SELECT * FROM announcements ORDER BY on_home DESC, sort, id DESC").fetchall()
    eid = request.args.get("ndrysho", type=int)
    edit = con.execute("SELECT * FROM announcements WHERE id=?", (eid,)).fetchone() if eid else (None if request.args.get("re") else (rows[0] if rows else None))
    return _ads_page(rows, edit, {}, {})


def _ads_page(rows, edit, form, errors, status=200):
    t = now_iso()

    def state(r):
        if not r["published"]:
            return ("Draft", "neutral")
        if r["starts_at"] and r["starts_at"] > t:
            return ("Planifikuar", "info")
        if r["ends_at"] and r["ends_at"] < t:
            return ("Skaduar", "warning")
        return ("Publikuar", "success")
    preview = content.view(edit) if edit else None
    home_n = sum(1 for r in rows if r["on_home"] and state(r)[0] == "Publikuar")
    return page("admin/ads.html", "ads", "Reklamat & Njoftimet", "Paneli › Marketingu", rows=rows, edit=edit, form=form, errors=errors, state=state,
                types=TYPE_OPTS, tones={k: v[0] for k, v in content.TYPES.items()}, labels=dict(TYPE_OPTS), preview=preview, home_n=home_n), status


@bp.post("/reklamat")
@auth.requires("ads")
def ad_save():
    con = get_db()
    f = request.form
    aid = f.get("id", type=int)
    row = con.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone() if aid else None
    errors, d = {}, {}
    d["type"] = f.get("type") if f.get("type") in content.TYPES else "njoftim"
    for k, n in (("title_sq", 140), ("title_en", 140), ("summary_sq", 300), ("summary_en", 300), ("body_sq", 6000), ("body_en", 6000),
                 ("link_label", 40), ("job_position", 80), ("job_schedule", 80), ("job_place", 80), ("job_deadline", 40)):
        d[k] = (f.get(k) or "").strip()[:n]
    link = (f.get("link") or "").strip()[:300]
    if link and not (link.startswith("/") and not link.startswith("//")) and not link.startswith("https://"):
        errors["link"] = "Lidhja: rrugë e faqes (p.sh. /oferta) ose https://…"
    d["link"] = link
    if len(d["title_sq"]) < 2:
        errors["title_sq"] = "Shkruani titullin."
    try:
        d["starts_at"] = _parse_dt(f.get("starts_at"))
        d["ends_at"] = _parse_dt(f.get("ends_at"), end=True)
        if d["starts_at"] and d["ends_at"] and d["starts_at"] > d["ends_at"]:
            errors["ends_at"] = "Mbarimi duhet të jetë pas fillimit."
    except ValueError:
        errors["starts_at"] = "Data nuk është e vlefshme."
    d["published"] = 1 if f.get("published") == "1" else 0
    d["on_home"] = 1 if f.get("on_home") == "1" else 0
    d["image_contain"] = 1 if f.get("image_contain") == "1" else 0
    try:
        d["sort"] = int(f.get("sort") or 0)
    except ValueError:
        d["sort"] = 0
    fobj = request.files.get("image")
    img = None
    if not errors and fobj and fobj.filename:
        try:
            img = images.save_announcement_image(fobj)
        except images.ImageError as e:
            errors["image"] = str(e)
    if errors:
        rows = con.execute("SELECT * FROM announcements ORDER BY on_home DESC, sort, id DESC").fetchall()
        return _ads_page(rows, row, f, errors, 422)
    t = now_iso()
    with transaction(con):
        if row:
            con.execute("UPDATE announcements SET %s, updated_at=? WHERE id=?" % ", ".join("%s=?" % k for k in d), list(d.values()) + [t, aid])
            if img:
                con.execute("UPDATE announcements SET image=? WHERE id=?", (img, aid))
                images.delete(row["image"])
            audit.log("Ndryshoi njoftim", d["title_sq"], area="ads", con=con)
        else:
            d["image"] = img or ""
            cols = list(d.keys()) + ["created_at", "updated_at"]
            aid = con.execute("INSERT INTO announcements(%s) VALUES (%s)" % (", ".join(cols), ", ".join("?" * len(cols))), list(d.values()) + [t, t]).lastrowid
            audit.log("Krijoi njoftim", d["title_sq"], area="ads", tone="new", con=con)
        n_home = con.execute("SELECT COUNT(*) FROM announcements WHERE on_home=1 AND " + content.ACTIVE_SQL, (t, t)).fetchone()[0]
    if n_home > 4:
        flash("Ruajtur. Kujdes: %d njoftime janë në ballinë — shfaqen vetëm 4 të parat sipas renditjes." % n_home, "info")
    else:
        flash("Njoftimi u ruajt.", "success")
    return redirect(url_for("admin.ads", ndrysho=aid))


@bp.post("/reklamat/<int:aid>/fshi")
@auth.requires("ads")
def ad_delete(aid):
    con = get_db()
    r = con.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone() or abort(404)
    with transaction(con):
        con.execute("DELETE FROM announcements WHERE id=?", (aid,))
        audit.log("Fshiu njoftim", r["title_sq"], area="ads", tone="danger", con=con)
    images.delete(r["image"])
    flash("Njoftimi u fshi.", "success")
    return redirect(url_for("admin.ads"))


@bp.post("/reklamat/<int:aid>/ballina")
@auth.requires("ads")
def ad_home(aid):
    con = get_db()
    r = con.execute("SELECT * FROM announcements WHERE id=?", (aid,)).fetchone() or abort(404)
    con.execute("UPDATE announcements SET on_home=?, updated_at=? WHERE id=?", (0 if r["on_home"] else 1, now_iso(), aid))
    audit.log("Ndryshoi ballinën", r["title_sq"], after="në ballinë" if not r["on_home"] else "jo në ballinë", area="ads", con=con)
    return _back("U ruajt.")


@bp.post("/reklamat/renditja")
@auth.requires("ads")
def ad_order():
    con = get_db()
    ids = [int(x) for x in request.form.getlist("order") if x.isdigit()]
    with transaction(con):
        for i, aid in enumerate(ids, 1):
            con.execute("UPDATE announcements SET sort=? WHERE id=?", (i, aid))
    return {"ok": True}


# ---------------- reports ----------------

@bp.get("/raportet")
@auth.requires("reports")
def reports():
    con = get_db()
    today = now().date()
    mode = request.args.get("periudha", "javore")
    d1s, d2s = request.args.get("nga", ""), request.args.get("deri", "")
    span = {"ditore": 1, "javore": 14, "mujore": 30}.get(mode, 14)
    try:
        d1 = date.fromisoformat(d1s) if mode == "interval" and d1s else today - timedelta(days=span - 1)
        d2 = date.fromisoformat(d2s) if mode == "interval" and d2s else today
    except ValueError:
        d1, d2 = today - timedelta(days=13), today
    if d1 > d2:
        d1, d2 = d2, d1
    if (d2 - d1).days > 366:
        d1 = d2 - timedelta(days=366)
    days = (d2 - d1).days + 1
    p1, p2 = d1 - timedelta(days=days), d1 - timedelta(days=1)
    q = "SELECT COUNT(*), COALESCE(SUM(total),0) FROM orders WHERE status<>'cancel' AND created_at >= ? AND created_at < ?"
    n, rev = con.execute(q, (d1.isoformat(), (d2 + timedelta(days=1)).isoformat())).fetchone()
    pn, prev = con.execute(q, (p1.isoformat(), (p2 + timedelta(days=1)).isoformat())).fetchone()
    cancelled = con.execute("SELECT COUNT(*) FROM orders WHERE status='cancel' AND created_at >= ? AND created_at < ?", (d1.isoformat(), (d2 + timedelta(days=1)).isoformat())).fetchone()[0]
    per_day = {r[0]: (r[1], r[2]) for r in con.execute("SELECT substr(created_at,1,10), COUNT(*), SUM(total) FROM orders WHERE status<>'cancel' AND created_at >= ? AND created_at < ? GROUP BY 1",
                                                       (d1.isoformat(), (d2 + timedelta(days=1)).isoformat()))}
    series = [(d1 + timedelta(days=i)) for i in range(days)]
    cash = [per_day.get(d.isoformat(), (0, 0))[0] for d in series]
    labels = [d.strftime("%d") for d in series]
    best = con.execute("""SELECT i.name, SUM(i.qty) q, MAX(i.image) img FROM order_items i JOIN orders o ON o.id=i.order_id
                          WHERE o.status<>'cancel' AND o.created_at >= ? AND o.created_at < ? GROUP BY i.sku, i.name ORDER BY q DESC LIMIT 5""",
                       (d1.isoformat(), (d2 + timedelta(days=1)).isoformat())).fetchall()
    table = [(d, per_day[d.isoformat()]) for d in reversed(series) if d.isoformat() in per_day]
    if request.args.get("eksporto") == "csv":
        return _csv("raporti-%s-%s.csv" % (d1, d2), ["Data", "Porosi", "Të ardhura (L)", "Mesatarja (L)", "Cash", "Kartë"],
                    [[fmt_date(d.isoformat()), v[0], v[1], v[1] // v[0] if v[0] else 0, v[0], 0] for d, v in table])

    def pct(a, b):
        return None if not b else (a - b) * 100.0 / b
    return page("admin/reports.html", "reports", "Raportet", "Paneli › Sistemi", mode=mode, d1=d1, d2=d2, n=n, rev=rev, pn=pn, prev=prev, cancelled=cancelled,
                chart=bar_chart(cash, [0] * len(cash), labels), best=best, table=table, pct=pct, avg=(rev // n) if n else 0, pavg=(prev // pn) if pn else 0)
