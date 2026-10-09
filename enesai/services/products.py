"""Product + category writes (admin). Keeps derived columns (sale_price, search_text) in sync."""
import re

from ..db import get_db
from ..util import discounted, norm, now_iso, slugify
from . import audit
from .catalog import DISCOUNTS, build_search_text

SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$")


def parse_int(v, default=None):
    s = re.sub(r"[\s.]", "", str(v if v is not None else ""))
    if s == "":
        return default
    if not re.match(r"^-?\d+$", s):
        raise ValueError(v)
    return int(s)


def validate(f, pid=None, con=None):
    con = con or get_db()
    err, d = {}, {}
    d["name_sq"] = (f.get("name_sq") or "").strip()[:160]
    d["name_en"] = (f.get("name_en") or "").strip()[:160]
    d["desc_sq"] = (f.get("desc_sq") or "").strip()[:4000]
    d["desc_en"] = (f.get("desc_en") or "").strip()[:4000]
    d["brand"] = (f.get("brand") or "").strip()[:80]
    d["packaging"] = (f.get("packaging") or "").strip()[:60]
    d["unit"] = f.get("unit") if f.get("unit") in ("copë", "kg", "L", "pako") else "copë"
    d["barcode"] = re.sub(r"\s", "", f.get("barcode") or "")[:20]
    d["sku"] = (f.get("sku") or "").strip()[:40]
    if len(d["name_sq"]) < 2:
        err["name_sq"] = "Shkruani emrin e produktit."
    if not SKU_RE.match(d["sku"]):
        err["sku"] = "SKU: shkronja, shifra, “-”, “_”, “.” (deri 40)."
    elif con.execute("SELECT 1 FROM products WHERE sku = ? AND id <> ?", (d["sku"], pid or 0)).fetchone():
        err["sku"] = "Ky SKU ekziston te një produkt tjetër."
    if d["barcode"] and not d["barcode"].isdigit():
        err["barcode"] = "Barkodi ka vetëm shifra."
    try:
        d["price"] = parse_int(f.get("price"))
        if not d["price"] or d["price"] <= 0 or d["price"] > 10_000_000:
            raise ValueError
    except (ValueError, TypeError):
        err["price"] = "Çmimi: numër i plotë në lek, p.sh. 2370."
        d["price"] = None
    try:
        d["discount_pct"] = parse_int(f.get("discount_pct"), 0)
        if d["discount_pct"] not in DISCOUNTS:
            raise ValueError
    except ValueError:
        err["discount_pct"] = "Zgjidhni një nga zbritjet e lejuara."
        d["discount_pct"] = 0
    for k, lbl in (("stock", "Stoku"), ("low_threshold", "Pragu")):
        try:
            d[k] = parse_int(f.get(k), 0 if k == "stock" else 5)
            if d[k] < 0 or d[k] > 10_000_000:
                raise ValueError
        except ValueError:
            err[k] = "%s: numër i plotë ≥ 0." % lbl
            d[k] = 0
    d["visible"] = 1 if f.get("visible") == "1" else 0
    d["on_offers"] = 1 if f.get("on_offers") == "1" else 0
    d["allow_backorder"] = 1 if f.get("allow_backorder") == "1" else 0
    try:
        d["category_id"] = int(f.get("category_id") or 0)
    except ValueError:
        d["category_id"] = 0
    cat = con.execute("SELECT * FROM categories WHERE id = ? AND parent_id IS NULL", (d["category_id"],)).fetchone()
    if not cat:
        err["category_id"] = "Zgjidhni kategorinë."
    try:
        sub = int(f.get("subcategory_id") or 0)
    except ValueError:
        sub = 0
    d["subcategory_id"] = None
    if sub and cat:
        if con.execute("SELECT 1 FROM categories WHERE id=? AND parent_id=?", (sub, cat["id"])).fetchone():
            d["subcategory_id"] = sub
        else:
            err["subcategory_id"] = "Nënkategoria nuk i përket kategorisë."
    return d, err


def _derived(d, con):
    names = [r[0] for r in con.execute("SELECT name_sq FROM categories WHERE id IN (?, ?)", (d["category_id"], d.get("subcategory_id") or 0))]
    d["sale_price"] = discounted(d["price"], d["discount_pct"])
    d["search_text"] = build_search_text(d["name_sq"], d["name_en"], d["brand"], d["sku"], d["packaging"], names)
    return d


COLS = ["sku", "name_sq", "name_en", "desc_sq", "desc_en", "brand", "packaging", "unit", "barcode", "price", "discount_pct", "sale_price",
        "stock", "low_threshold", "allow_backorder", "visible", "on_offers", "category_id", "subcategory_id", "search_text"]


def insert(d, con=None):
    con = con or get_db()
    d = _derived(d, con)
    t = now_iso()
    cur = con.execute("INSERT INTO products(%s, created_at, updated_at) VALUES (%s, ?, ?)" % (", ".join(COLS), ", ".join("?" * len(COLS))),
                      [d[c] for c in COLS] + [t, t])
    return cur.lastrowid


def update(pid, d, con=None):
    con = con or get_db()
    d = _derived(d, con)
    con.execute("UPDATE products SET %s, updated_at = ? WHERE id = ?" % ", ".join("%s = ?" % c for c in COLS), [d[c] for c in COLS] + [now_iso(), pid])


def set_discount(ids, pct, con=None):
    con = con or get_db()
    if pct not in DISCOUNTS:
        raise ValueError(pct)
    for pid in ids:
        r = con.execute("SELECT price, discount_pct, name_sq, sku FROM products WHERE id=?", (pid,)).fetchone()
        if not r:
            continue
        con.execute("UPDATE products SET discount_pct=?, sale_price=?, updated_at=? WHERE id=?", (pct, discounted(r["price"], pct), now_iso(), pid))
        if r["discount_pct"] != pct:
            audit.log("Vendosi zbritje", "%s (%s)" % (r["name_sq"], r["sku"]), "%d%%" % r["discount_pct"], "%d%%" % pct, area="products", tone="new", con=con)


def recompute_search(con, category_id=None):
    """After a category rename the product search text is rebuilt (batched, SQL-side lookups)."""
    q = "SELECT id, name_sq, name_en, brand, sku, packaging, category_id, subcategory_id FROM products"
    args = ()
    if category_id:
        q += " WHERE category_id=? OR subcategory_id=?"
        args = (category_id, category_id)
    names = {r[0]: r[1] for r in con.execute("SELECT id, name_sq FROM categories")}
    for r in con.execute(q, args).fetchall():
        st = build_search_text(r["name_sq"], r["name_en"], r["brand"], r["sku"], r["packaging"],
                               [names.get(r["category_id"], ""), names.get(r["subcategory_id"], "")])
        con.execute("UPDATE products SET search_text=? WHERE id=?", (st, r["id"]))


def unique_slug(name, con, exclude=None, parent_slug=None):
    base = slugify(name)
    if parent_slug:
        base = parent_slug + "-" + base
    s, i = base, 2
    while con.execute("SELECT 1 FROM categories WHERE slug=? AND id<>?", (s, exclude or 0)).fetchone():
        s = "%s-%d" % (base, i)
        i += 1
    return s
