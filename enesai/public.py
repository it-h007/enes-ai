"""Public blueprint: storefront pages (server-rendered; JS only enhances)."""
import re
from pathlib import Path
from urllib.parse import quote, urlencode

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.security import safe_join

from .i18n import _
from .services import cart as cartsvc
from .services import catalog, content
from .services import settings as st
from .util import text_to_html

bp = Blueprint("public", __name__)


@bp.app_context_processor
def _commerce_ctx():
    return {"sort_labels": catalog.SORT_LABELS, "adult_checkout": current_app.config["ADULT_CHECKOUT_ENABLED"]}


@bp.get("/")
def home():
    return render_template("pages/index.html", active="home", home_categories=catalog.categories(),
                           home_announcements=content.home_announcements(), canonical=_abs("/"))


# ---------------- listing helpers ----------------

def _int_arg(name):
    v = request.args.get(name, "")
    v = re.sub(r"[^\d]", "", v)
    return int(v) if v else None


def _parse_filters(base):
    a = request.args
    stok_vals = a.getlist("stok")
    f = {
        "base": base, "q": (a.get("q") or "").strip()[:80],
        "cat_slugs": [s for s in a.getlist("kategoria") if s][:30],
        "sub_slugs": [s for s in a.getlist("nenkategoria") if s][:60],
        "sale": a.get("oferta") == "1",
        "stock": ("1" in stok_vals) if stok_vals else True,  # design default: “Vetëm në stok” on
        "pmin": _int_arg("cmimi_min"), "pmax": _int_arg("cmimi_max"),
        "sort": a.get("rendit") if a.get("rendit") in catalog.SORTS else "te-rejat",
        "page": _int_arg("faqe") or 1, "fav": a.get("te-preferuarat") == "1",
        "ids": ",".join(re.findall(r"\d+", a.get("ids", "")))[:2000],
    }
    return f


def _url(base, params):
    qs = urlencode([(k, v) for k, v in params if v not in (None, "", False)], doseq=True)
    return base + ("?" + qs if qs else "")


def _params(f, drop=None, page=None):
    p = []
    if f["q"]:
        p.append(("q", f["q"]))
    if f.get("fav"):
        p.append(("te-preferuarat", "1"))
        p.append(("ids", f.get("ids")))
    for s in f["cat_slugs"]:
        if drop != ("kategoria", s):
            p.append(("kategoria", s))
    for s in f["sub_slugs"]:
        if drop != ("nenkategoria", s):
            p.append(("nenkategoria", s))
    if f["sale"] and drop != ("oferta",):
        p.append(("oferta", "1"))
    if not f["stock"] and drop != ("stok",):
        p.append(("stok", "0"))
    if f["pmin"] is not None and drop != ("cmimi",):
        p.append(("cmimi_min", f["pmin"]))
    if f["pmax"] is not None and drop != ("cmimi",):
        p.append(("cmimi_max", f["pmax"]))
    if f["sort"] != f.get("default_sort", "te-rejat"):
        p.append(("rendit", f["sort"]))
    if page and page > 1:
        p.append(("faqe", page))
    return p


def _listing_page(title, lead, crumbs, base, rail_active="all", category=None, sub=None, active="shop", fixed_ids=None):
    f = _parse_filters(base)
    cats = catalog.categories()
    by_slug = {c["slug"]: c for c in cats}
    sub_by_slug = {s["slug"]: s for c in cats for s in c["subs"]}
    q = {"q": f["q"], "sale": f["sale"], "stock": f["stock"], "pmin": f["pmin"], "pmax": f["pmax"], "sort": f["sort"], "page": f["page"]}
    if fixed_ids is not None:
        q["ids"] = fixed_ids
    cat_ids = [by_slug[s]["pk"] for s in f["cat_slugs"] if s in by_slug]
    if category:
        cat_ids = [category["pk"]]
        if category["slug"] not in f["cat_slugs"]:
            f["cat_slugs"] = [category["slug"]] + f["cat_slugs"]
    if cat_ids:
        q["cats"] = cat_ids
    sub_ids = [sub_by_slug[s]["pk"] for s in f["sub_slugs"] if s in sub_by_slug]
    if sub:
        sub_ids = [sub["pk"]]
    if sub_ids:
        q["subs"] = sub_ids
    listing = catalog.list_products(q)
    f["has_filters"] = bool(f["q"] or f["sale"] or f["pmin"] is not None or f["pmax"] is not None or sub_ids or len(f["cat_slugs"]) > (1 if category else 0))
    f["clear_url"] = base + (("?te-preferuarat=1&ids=" + f["ids"]) if f["fav"] else "")
    chips = []
    if f["q"]:
        chips.append(("“%s”" % f["q"], _url(base, [x for x in _params(f) if x[0] != "q"])))
    for s in f["cat_slugs"]:
        if s in by_slug and not (category and s == category["slug"]):
            chips.append((by_slug[s]["name"], _url(base, _params(f, ("kategoria", s)))))
        elif category and s == category["slug"]:
            chips.append((by_slug[s]["name"], "/dyqani"))
    for s in f["sub_slugs"]:
        if s in sub_by_slug:
            chips.append((sub_by_slug[s]["name"], _url(base, _params(f, ("nenkategoria", s)))))
    if sub:
        chips.append((sub["name"], "/kategoria/" + category["slug"]))
    if f["sale"]:
        chips.append((_("Në ofertë"), _url(base, _params(f, ("oferta",)))))
    if f["stock"]:
        chips.append((_("Vetëm në stok"), _url(base, _params(dict(f, stock=False)))))
    if f["pmin"] is not None or f["pmax"] is not None:
        chips.append(("%s – %s L" % (f["pmin"] or 0, f["pmax"] if f["pmax"] is not None else "…"), _url(base, _params(f, ("cmimi",)))))

    def page_url(n):
        return _url(base, _params(f, page=n))

    if request.args.get("partial") == "1":
        # “Shfaq 24 të tjera”: grid fragment for the touch load-more button
        html = render_template("partials/grid_items.html", items=listing["items"])
        nxt = page_url(listing["page"] + 1) if listing["page"] < listing["pages"] else None
        return jsonify(html=html, next=nxt, shown=min(listing["total"], listing["page"] * listing["per_page"]), total=listing["total"])

    subchips = None
    if category and category["subs"]:
        subchips = [("%s · %s" % (_("Të gjitha"), category["count"]), "/kategoria/" + category["slug"], sub is None)]
        subchips += [("%s · %s" % (s["name"], s["count"]), "/kategoria/%s/%s" % (category["slug"], s["slug"]), sub is not None and sub["slug"] == s["slug"]) for s in category["subs"]]
    total_all = sum(c["count"] for c in cats)
    return render_template("pages/dyqani.html", active=active, title=title, lead=lead, crumbs_list=crumbs, f=f,
                           filter_cats=cats, total_all=total_all, listing=listing, chips=chips, page_url=page_url,
                           rail_active=rail_active, subchips=subchips, category=category, search_value=f["q"],
                           load_more_mode=bool(category), canonical=_abs(base), noindex=bool(f["q"] or request.args))


@bp.get("/dyqani")
def shop():
    q = (request.args.get("q") or "").strip()
    if request.args.get("te-preferuarat") == "1":
        ids = [int(x) for x in re.findall(r"\d+", request.args.get("ids", ""))][:200]
        return _listing_page(_("Të preferuarat"), _("Produktet që keni shënuar me zemër në këtë shfletues."),
                             [(_("Ballina"), "/"), (_("Të preferuarat"),)], "/dyqani", fixed_ids=ids)
    title = _("Dyqani Online")
    return _listing_page(title, _("Zgjidhni produktet tuaja dhe porositni me dërgesë në shtëpi në %(c)s.", c=st.get("city") or "Vlorë"),
                         [(_("Ballina"), "/"), (_("Dyqani Online"),)] if not q else [(_("Ballina"), "/"), (_("Dyqani Online"), "/dyqani"), (_("Kërkimi"),)],
                         "/dyqani")


@bp.get("/te-preferuarat")
def favourites():
    # C-21: no separate page was designed — the shop lists the ids stored in this browser.
    return redirect("/dyqani?te-preferuarat=1")


@bp.get("/kategoria/<slug>")
@bp.get("/kategoria/<slug>/<sub>")
def category(slug, sub=None):
    c = catalog.category_by_slug(slug)
    if not c or c["parent_id"] is not None:
        abort(404)
    s = None
    if sub:
        s = next((x for x in c["subs"] if x["slug"] == sub), None)
        if not s:
            abort(404)
    lead = _("Shfletoni produktet e kategorisë %(c)s.", c=c["name"])
    crumbs = [(_("Ballina"), "/"), (_("Kategoritë"), "/kategorite"), (c["name"],)] if not s else \
        [(_("Ballina"), "/"), (_("Kategoritë"), "/kategorite"), (c["name"], "/kategoria/" + c["slug"]), (s["name"],)]
    base = "/kategoria/" + c["slug"] + ("/" + s["slug"] if s else "")
    return _listing_page(s["name"] if s else c["name"], lead, crumbs, base, rail_active=c["slug"], category=c, sub=s, active="cats")


@bp.get("/kategorite")
def categories_page():
    cats = list(catalog.categories())
    sort = request.args.get("rendit", "dyqani")
    if sort == "az":
        cats.sort(key=lambda c: c["name"].lower())
    elif sort == "produkte":
        cats.sort(key=lambda c: -c["count"])
    return render_template("pages/kategorite.html", active="cats", cats=cats, sub_total=sum(len(c["subs"]) for c in cats), sort=sort,
                           canonical=_abs("/kategorite"))


@bp.get("/oferta")
def offers():
    sort = request.args.get("rendit") if request.args.get("rendit") in catalog.SORTS else "zbritja"
    active_cat = request.args.get("kategoria") or None
    cats = catalog.categories()
    con_counts = {}
    from .db import get_db
    for r in get_db().execute("""SELECT p.category_id, COUNT(*) n FROM products p JOIN categories c ON c.id=p.category_id
                                 WHERE p.visible=1 AND c.visible=1 AND p.discount_pct>0 AND p.on_offers=1 GROUP BY p.category_id"""):
        con_counts[r["category_id"]] = r["n"]
    offer_cats = [(c, con_counts[c["pk"]]) for c in cats if con_counts.get(c["pk"])]
    q = {"sale": True, "offers_page": True, "sort": sort, "page": _int_arg("faqe") or 1}
    sel = next((c for c in cats if c["slug"] == active_cat), None)
    if sel:
        q["cats"] = [sel["pk"]]
    listing = catalog.list_products(q)

    def tab_url(slug):
        return _url("/oferta", [("kategoria", slug), ("rendit", sort if sort != "zbritja" else None)])

    def page_url(n):
        return _url("/oferta", [("kategoria", active_cat), ("rendit", sort if sort != "zbritja" else None), ("faqe", n if n > 1 else None)])

    return render_template("pages/oferta.html", active="offers", listing=listing, offer_cats=offer_cats,
                           offer_total=sum(con_counts.values()), active_cat=sel["slug"] if sel else None, sort=sort,
                           tab_url=tab_url, page_url=page_url, canonical=_abs("/oferta"))


@bp.get("/produkt/<int:pid>")
@bp.get("/produkt/<int:pid>/<path:_slug>")
def product(pid, _slug=None):
    p = catalog.get_product(pid)
    if not p:
        abort(404)
    from .db import get_db
    raw = get_db().execute("SELECT allow_backorder FROM products WHERE id=?", (pid,)).fetchone()
    maxq = current_app.config["MAX_QTY_PER_LINE"] if raw["allow_backorder"] else max(0, min(current_app.config["MAX_QTY_PER_LINE"], p["qty"]))
    return render_template("pages/produkt.html", active="shop", p=p, maxq=maxq, related=catalog.related(p),
                           canonical=_abs("/produkt/%d" % pid))


# ---------------- cart pages ----------------

@bp.get("/shporta")
def cart_page():
    lines = cartsvc.lines()
    s = st.all_settings()
    return render_template("pages/shporta.html", active="shop", lines=lines, t=cartsvc.cart_totals(lines),
                           fee=st.int_setting("fee", 0, s), free_over=st.int_setting("freeOver", 0, s), noindex=True)


# ---------------- info pages ----------------

@bp.get("/rreth-nesh")
def about():
    return render_template("pages/rreth_nesh.html", active="about", canonical=_abs("/rreth-nesh"))


@bp.get("/kontakt")
def contact():
    s = st.all_settings()
    embed, directions = None, None
    if s.get("store_lat") and s.get("store_lng"):
        ll = "%s,%s" % (s["store_lat"], s["store_lng"])
        embed = "https://www.google.com/maps?q=%s&z=17&output=embed" % quote(ll)
        directions = "https://www.google.com/maps/dir/?api=1&destination=%s" % quote(ll)
    if not directions:
        directions = s.get("maps_link") or "https://www.google.com/maps/dir/?api=1&destination=" + quote("ENES’AI Super Market Vlorë")
    return render_template("pages/kontakt.html", active="contact", embed_url=embed, directions_url=directions, canonical=_abs("/kontakt"))


@bp.get("/kushtet")
def terms():
    return render_template("pages/kushtet.html", active=None, terms_updated=st.get("terms_updated") or "08.10.2026", canonical=_abs("/kushtet"))


@bp.get("/privatesia")
def privacy():
    return redirect("/kushtet#privatesia", code=301)  # C-38


@bp.get("/njoftime")
def news():
    t = request.args.get("lloji")
    t = t if t in content.TYPES else None
    data = content.public_list(t, _int_arg("faqe") or 1)

    def page_url(n):
        return _url("/njoftime", [("lloji", t), ("faqe", n if n > 1 else None)])

    return render_template("pages/njoftime.html", active="news", data=data, type_=t, page_url=page_url, canonical=_abs("/njoftime"))


@bp.get("/njoftime/<int:aid>")
def news_detail(aid):
    n = content.get_public(aid)
    if not n:
        abort(404)
    return render_template("pages/njoftim.html", active="news", n=n, body_html=text_to_html(n["body"] or n["text"]))


# ---------------- SEO + media ----------------

@bp.get("/robots.txt")
def robots():
    admin = current_app.config["ADMIN_PATH"]
    lines = ["User-agent: *", "Disallow: /arka", "Disallow: /porosia/", "Disallow: /shporta", "Disallow: /api/"]
    if admin == "/paneli":  # a custom (obscured) admin path is not advertised here
        lines.append("Disallow: /paneli")
    lines.append("Sitemap: " + _abs("/sitemap.xml"))
    return current_app.response_class("\n".join(lines) + "\n", mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():
    from .db import get_db
    urls = [_abs(u) for u in ("/", "/dyqani", "/oferta", "/kategorite", "/rreth-nesh", "/njoftime", "/kontakt", "/kushtet")]
    for c in catalog.categories():
        urls.append(_abs("/kategoria/" + c["slug"]))
    for r in get_db().execute("SELECT p.id FROM products p JOIN categories c ON c.id=p.category_id WHERE p.visible=1 AND c.visible=1 ORDER BY p.id LIMIT 45000"):
        urls.append(_abs("/produkt/%d" % r["id"]))
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + \
        "".join("<url><loc>%s</loc></url>\n" % u for u in urls) + "</urlset>\n"
    return current_app.response_class(body, mimetype="application/xml")


@bp.get("/media/<path:path>")
def media(path):
    """Public uploads (product/category/announcement images, logos). Private files
    (invoices, imports) live in instance/private and are never served here."""
    root = current_app.config["UPLOAD_DIR"]
    full = safe_join(str(root), path)
    if not full or not Path(full).is_file() or Path(full).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        abort(404)
    resp = send_from_directory(root, path, max_age=60 * 60 * 24 * 30)
    return resp


def _abs(path):
    base = current_app.config.get("PUBLIC_BASE_URL") or request.host_url.rstrip("/")
    return base + path
