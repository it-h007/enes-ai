"""Catalogue queries: categories tree, product listing with filters/sort/paging, search.

Large-catalogue safe: every list is paged in SQL (LIMIT/OFFSET on indexed columns),
counts use COUNT(*), search uses FTS5 when present and LIKE on the normalised column
otherwise. Nothing loads the whole product table into memory."""
import math

from flask import g

from ..db import fts_available, get_db
from ..i18n import lang
from ..util import discounted, norm

PER_PAGE = 24
SORTS = {
    "te-rejat": "p.id DESC",
    "cmimi-asc": "p.sale_price ASC, p.id DESC",
    "cmimi-desc": "p.sale_price DESC, p.id DESC",
    "zbritja": "p.discount_pct DESC, p.id DESC",
    "emri": "p.name_sq COLLATE NOCASE ASC, p.id",
}
SORT_LABELS = [("te-rejat", "Më të rejat"), ("cmimi-asc", "Çmimi: nga më i ulëti"), ("cmimi-desc", "Çmimi: nga më i larti"),
               ("zbritja", "Zbritja më e madhe"), ("emri", "Emri A–Z")]
DISCOUNTS = (0, 5, 10, 15, 20, 25, 30, 40, 50)


def media_url(path):
    if not path:
        return ""
    if path.startswith(("/", "http://", "https://")):
        return path
    return "/media/" + path


# ---------------- categories ----------------

def _cat_view(r, counts):
    en = lang() == "en"
    return {
        "id": r["slug"], "pk": r["id"], "slug": r["slug"],
        "name": (r["name_en"] if en and r["name_en"] else r["name_sq"]),
        "name_sq": r["name_sq"], "name_en": r["name_en"],
        "img": media_url(r["image"]), "image": r["image"], "adult": bool(r["adult"]),
        "visible": bool(r["visible"]), "sort": r["sort"], "parent_id": r["parent_id"],
        "count": counts.get(r["id"], 0), "subs": [],
    }


def category_counts(con=None):
    """Visible product count per category id (main + sub)."""
    con = con or get_db()
    counts = {}
    for r in con.execute("SELECT category_id, COUNT(*) n FROM products WHERE visible=1 GROUP BY category_id"):
        counts[r["category_id"]] = r["n"]
    for r in con.execute("SELECT subcategory_id, COUNT(*) n FROM products WHERE visible=1 AND subcategory_id IS NOT NULL GROUP BY subcategory_id"):
        counts[r["subcategory_id"]] = r["n"]
    return counts


def categories(include_hidden=False, con=None):
    """Top-level categories (admin order) each with .subs; cached per request."""
    key = "cats_all" if include_hidden else "cats"
    if con is None and key in g:
        return g.get(key)
    db = con or get_db()
    counts = category_counts(db)
    rows = db.execute("SELECT * FROM categories %s ORDER BY sort, name_sq" % ("" if include_hidden else "WHERE visible=1")).fetchall()
    tops, by_id = [], {}
    for r in rows:
        if r["parent_id"] is None:
            c = _cat_view(r, counts)
            tops.append(c)
            by_id[r["id"]] = c
    for r in rows:
        if r["parent_id"] is not None and r["parent_id"] in by_id:
            by_id[r["parent_id"]]["subs"].append(_cat_view(r, counts))
    if con is None:
        setattr(g, key, tops)
    return tops


def category_by_slug(slug, include_hidden=False):
    r = get_db().execute("SELECT * FROM categories WHERE slug=?" + ("" if include_hidden else " AND visible=1"), (slug,)).fetchone()
    if not r:
        return None
    counts = category_counts()
    c = _cat_view(r, counts)
    if r["parent_id"] is None:
        c["subs"] = [_cat_view(s, counts) for s in get_db().execute(
            "SELECT * FROM categories WHERE parent_id=? AND visible=1 ORDER BY sort, name_sq", (r["id"],))]
    return c


# ---------------- products ----------------

def stock_state(r):
    if r["stock"] <= 0 and not r["allow_backorder"]:
        return "out"
    if r["stock"] <= r["low_threshold"]:
        return "low"
    return "in"


def product_view(r, images=None, cat=None):
    """Template-facing product (same field names as the design's demo objects)."""
    en = lang() == "en"
    pct = r["discount_pct"]
    price = r["sale_price"] or discounted(r["price"], pct)
    imgs = images if images is not None else ([r["image"]] if "image" in r.keys() and r["image"] else [])
    imgs = [media_url(i) for i in imgs if i]
    keys = r.keys()
    return {
        "id": r["id"], "slug": str(r["id"]), "sku": r["sku"],
        "name": (r["name_en"] if en and r["name_en"] else r["name_sq"]), "name_sq": r["name_sq"], "name_en": r["name_en"],
        "desc": (r["desc_en"] if en and r["desc_en"] else r["desc_sq"]),
        "pack": r["packaging"], "brand": r["brand"] or "—", "unit": r["unit"], "barcode": r["barcode"],
        "price": price, "list_price": r["price"], "old": r["price"] if pct else None, "pct": pct,
        "stock": stock_state(r), "qty": r["stock"], "low_threshold": r["low_threshold"],
        "visible": bool(r["visible"]), "image": imgs[0] if imgs else "", "images": imgs,
        "category_id": r["category_id"], "subcategory_id": r["subcategory_id"],
        "cat_name": r["cat_name"] if "cat_name" in keys else "", "cat_slug": r["cat_slug"] if "cat_slug" in keys else "",
        "cat_adult": bool(r["cat_adult"]) if "cat_adult" in keys else False,
        "sub_name": r["sub_name"] if "sub_name" in keys else "",
        "updated_at": r["updated_at"], "is_demo": bool(r["is_demo"]),
    }


BASE_SELECT = """SELECT p.*, c.slug AS cat_slug, c.name_sq AS cat_name_sq, c.name_en AS cat_name_en, c.adult AS cat_adult, c.visible AS cat_visible,
  CASE WHEN ? = 'en' AND c.name_en <> '' THEN c.name_en ELSE c.name_sq END AS cat_name,
  s.name_sq AS sub_name,
  (SELECT path FROM product_images i WHERE i.product_id = p.id ORDER BY sort, id LIMIT 1) AS image
FROM products p JOIN categories c ON c.id = p.category_id LEFT JOIN categories s ON s.id = p.subcategory_id"""


def search_tokens(q):
    return [t for t in norm(q).replace('"', " ").split() if t][:8]


def _search_clause(q, con, where, args):
    toks = search_tokens(q)
    if not toks:
        return
    if fts_available(con):
        # prefix match on every token; FTS tokenizer folds diacritics too
        expr = " AND ".join('"%s"*' % t.replace('"', "") for t in toks)
        where.append("p.id IN (SELECT rowid FROM products_fts WHERE products_fts MATCH ?)")
        args.append(expr)
    else:
        for t in toks:
            where.append("p.search_text LIKE ? ESCAPE '\\'")
            args.append("%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")


def list_products(f, con=None, public=True, per_page=PER_PAGE):
    """f: dict with q, cats (list of category ids), subs (list), sale, stock, pmin, pmax, sort, page, ids."""
    con = con or get_db()
    where, args = [], [lang()]
    if public:
        where.append("p.visible = 1 AND c.visible = 1")
    if f.get("cats"):
        ids = [int(i) for i in f["cats"]]
        where.append("p.category_id IN (%s)" % ",".join("?" * len(ids)))
        args += ids
    if f.get("subs"):
        ids = [int(i) for i in f["subs"]]
        where.append("p.subcategory_id IN (%s)" % ",".join("?" * len(ids)))
        args += ids
    if f.get("ids") is not None:
        ids = [int(i) for i in f["ids"]][:200]
        where.append("p.id IN (%s)" % (",".join("?" * len(ids)) or "NULL"))
        args += ids
    if f.get("sale"):
        where.append("p.discount_pct > 0" + (" AND p.on_offers = 1" if f.get("offers_page") else ""))
    if f.get("stock"):
        where.append("(p.stock > 0 OR p.allow_backorder = 1)")
    if f.get("stock_state") == "low":
        where.append("p.stock > 0 AND p.stock <= p.low_threshold")
    elif f.get("stock_state") == "out":
        where.append("p.stock <= 0")
    elif f.get("stock_state") == "in":
        where.append("p.stock > p.low_threshold")
    elif f.get("stock_state") == "hidden":
        where.append("p.visible = 0")
    if f.get("pmin") is not None:
        where.append("p.sale_price >= ?"); args.append(int(f["pmin"]))
    if f.get("pmax") is not None:
        where.append("p.sale_price <= ?"); args.append(int(f["pmax"]))
    if f.get("q"):
        _search_clause(f["q"], con, where, args)
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    count_args = args[1:]
    total = con.execute("SELECT COUNT(*) FROM products p JOIN categories c ON c.id = p.category_id" + sql_where, count_args).fetchone()[0]
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, int(f.get("page") or 1)), pages)
    order = SORTS.get(f.get("sort") or "te-rejat", SORTS["te-rejat"])
    rows = con.execute(BASE_SELECT + sql_where + " ORDER BY " + order + " LIMIT ? OFFSET ?",
                       args + [per_page, (page - 1) * per_page]).fetchall()
    return {"items": [product_view(r) for r in rows], "total": total, "page": page, "pages": pages, "per_page": per_page}


def get_product(pid, public=True, con=None):
    con = con or get_db()
    r = con.execute(BASE_SELECT + " WHERE p.id = ?" + (" AND p.visible = 1 AND c.visible = 1" if public else ""), (lang(), pid)).fetchone()
    if not r:
        return None
    imgs = [i["path"] for i in con.execute("SELECT path FROM product_images WHERE product_id=? ORDER BY sort, id", (pid,))]
    return product_view(r, images=imgs)


def products_by_ids(ids, con=None):
    if not ids:
        return {}
    con = con or get_db()
    ids = [int(i) for i in ids]
    rows = con.execute(BASE_SELECT + " WHERE p.id IN (%s)" % ",".join("?" * len(ids)), [lang()] + ids).fetchall()
    return {r["id"]: (product_view(r), r) for r in rows}


def related(p, limit=5):
    """Same category first, then other visible products."""
    con = get_db()
    rows = con.execute(BASE_SELECT + " WHERE p.visible=1 AND c.visible=1 AND p.id<>? ORDER BY (p.category_id = ?) DESC, (p.stock > 0) DESC, p.id DESC LIMIT ?",
                       (lang(), p["id"], p["category_id"], limit)).fetchall()
    return [product_view(r) for r in rows]


def suggestions(q, limit=5):
    """Header search panel: up to 5 products + matching categories + total count."""
    con = get_db()
    res = list_products({"q": q, "sort": "emri"}, con=con, per_page=limit)
    nq = norm(q)
    cats = []
    for c in categories():
        for x in [c] + c["subs"]:
            if nq and nq in norm(x["name_sq"] + " " + x["name_en"]):
                cats.append({"name": x["name"], "url": "/kategoria/" + (c["slug"] + "/" + x["slug"] if x is not c else c["slug"])})
    return {"products": res["items"], "categories": cats[:4], "total": res["total"]}


def build_search_text(name_sq, name_en, brand, sku, packaging, cat_names=()):
    return norm(" ".join([name_sq or "", name_en or "", brand or "", sku or "", packaging or ""] + list(cat_names)))
