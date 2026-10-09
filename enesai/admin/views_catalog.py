"""Admin: products (list, bulk, form, images, delete / delete-all), categories, CSV import."""
import json
from pathlib import Path

from flask import Response, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from ..db import get_db, transaction
from ..services import audit, auth, csv_import, images
from ..services import products as psvc
from ..services.catalog import DISCOUNTS, categories, list_products, media_url, product_view
from ..util import discounted, now_iso
from . import bp
from .views_core import _csv, page

PER_PAGE_OPTS = (25, 50, 100)


# ---------------- products list ----------------

def _filters():
    a = request.args
    f = {"q": (a.get("q") or "").strip()[:80], "cat": a.get("kategoria", type=int), "stock_state": a.get("stoku") if a.get("stoku") in ("in", "low", "out", "hidden") else None,
         "sale": a.get("oferta") == "1", "per": a.get("per", 25, type=int), "page": a.get("faqe", 1, type=int), "sort": a.get("rendit") or "te-rejat"}
    if f["per"] not in PER_PAGE_OPTS:
        f["per"] = 25
    return f


@bp.get("/produktet")
@auth.requires("products")
def products():
    f = _filters()
    if request.args.get("eksporto") == "csv":
        return _export_catalog()
    q = {"q": f["q"], "sale": f["sale"], "stock_state": f["stock_state"], "page": f["page"], "sort": f["sort"]}
    if f["cat"]:
        q["cats"] = [f["cat"]]
    res = list_products(q, public=False, per_page=f["per"])
    con = get_db()
    raw = {r["id"]: r for r in con.execute("SELECT id, visible, updated_at, is_demo FROM products WHERE id IN (%s)" % (",".join(str(p["id"]) for p in res["items"]) or "0"))}
    counts = con.execute("SELECT COUNT(*), SUM(visible), SUM(discount_pct>0) FROM products").fetchone()

    def page_url(n):
        a = request.args.to_dict(); a["faqe"] = n
        return url_for("admin.products", **a)
    return page("admin/products.html", "prod", "Produktet", "Paneli › Menaxhimi", res=res, raw=raw, f=f, cats=categories(include_hidden=True),
                counts=counts, page_url=page_url, discounts=DISCOUNTS, per_opts=PER_PAGE_OPTS)


def _ids():
    try:
        return [int(x) for x in request.form.getlist("ids")][:1000]
    except ValueError:
        abort(400)


@bp.post("/produktet/bulk")
@auth.requires("products")
def products_bulk():
    ids, action = _ids(), request.form.get("action")
    if not ids:
        flash("Zgjidhni të paktën një produkt.", "info")
        return redirect(request.referrer or url_for("admin.products"))
    con = get_db()
    with transaction(con):
        if action == "discount":
            pct = request.form.get("pct", type=int)
            if pct not in DISCOUNTS:
                abort(400)
            psvc.set_discount(ids, pct, con)
            msg = "Zbritja −%d%% u vendos te %d produkte." % (pct, len(ids)) if pct else "Zbritja u hoq nga %d produkte." % len(ids)
        elif action in ("hide", "show"):
            con.execute("UPDATE products SET visible=?, updated_at=? WHERE id IN (%s)" % ",".join("?" * len(ids)), [0 if action == "hide" else 1, now_iso()] + ids)
            audit.log("Fshehu produkte" if action == "hide" else "Shfaqi produkte", "%d produkte" % len(ids), area="products", con=con)
            msg = "%d produkte u %s." % (len(ids), "fshehën" if action == "hide" else "shfaqën")
        elif action == "category":
            cid = request.form.get("category_id", type=int)
            if not con.execute("SELECT 1 FROM categories WHERE id=? AND parent_id IS NULL", (cid,)).fetchone():
                abort(400)
            con.execute("UPDATE products SET category_id=?, subcategory_id=NULL, updated_at=? WHERE id IN (%s)" % ",".join("?" * len(ids)), [cid, now_iso()] + ids)
            psvc.recompute_search(con, cid)
            audit.log("Ndryshoi kategorinë", "%d produkte" % len(ids), area="products", con=con)
            msg = "Kategoria u ndryshua për %d produkte." % len(ids)
        elif action == "delete":
            _delete(con, ids)
            msg = "%d produkte u fshinë. Porositë e vjetra e ruajnë emrin dhe çmimin." % len(ids)
        else:
            abort(400)
    flash(msg, "success")
    return redirect(request.referrer or url_for("admin.products"))


def _delete(con, ids):
    imgs = [r[0] for r in con.execute("SELECT path FROM product_images WHERE product_id IN (%s)" % ",".join("?" * len(ids)), ids)]
    names = [r[0] for r in con.execute("SELECT name_sq || ' (' || sku || ')' FROM products WHERE id IN (%s) LIMIT 5" % ",".join("?" * len(ids)), ids)]
    con.execute("DELETE FROM products WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)  # order_items keep snapshots (product_id → NULL)
    audit.log("Fshiu produkte", ", ".join(names) + (" …" if len(ids) > 5 else ""), area="products", tone="danger", con=con)
    for p in imgs:
        images.delete(p)


@bp.post("/produktet/<int:pid>/dukshem")
@auth.requires("products")
def product_visible(pid):
    con = get_db()
    r = con.execute("SELECT name_sq, sku, visible FROM products WHERE id=?", (pid,)).fetchone() or abort(404)
    v = 0 if r["visible"] else 1
    con.execute("UPDATE products SET visible=?, updated_at=? WHERE id=?", (v, now_iso(), pid))
    audit.log("Shfaqi produkt" if v else "Fshehu produkt", "%s (%s)" % (r["name_sq"], r["sku"]), area="products", con=con)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, visible=v)
    return redirect(request.referrer or url_for("admin.products"))


@bp.post("/produktet/<int:pid>/fshi")
@auth.requires("products")
def product_delete(pid):
    con = get_db()
    if not con.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone():
        abort(404)
    with transaction(con):
        if request.form.get("hide_instead") == "1":
            con.execute("UPDATE products SET visible=0, updated_at=? WHERE id=?", (now_iso(), pid))
            audit.log("Fshehu produkt", "#%d" % pid, area="products", con=con)
            flash("Produkti u fsheh nga dyqani.", "success")
        else:
            _delete(con, [pid])
            flash("Produkti u fshi.", "success")
    return redirect(url_for("admin.products"))


@bp.post("/produktet/fshi-te-gjitha")
@auth.requires("products_delete_all")
def products_delete_all():
    """V1-12: owner only, typed confirmation, catalogue CSV backup offered first."""
    if (request.form.get("confirm") or "").strip() != "FSHI TË GJITHA":
        flash("Shkruani saktë “FSHI TË GJITHA” për të konfirmuar.", "error")
        return redirect(url_for("admin.products", fshi=1))
    con = get_db()
    with transaction(con):
        n = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        imgs = [r[0] for r in con.execute("SELECT path FROM product_images")]
        con.execute("DELETE FROM products")
        audit.log("Fshiu të gjitha produktet", "%d produkte" % n, area="products", tone="danger", con=con)
    for p in imgs:
        images.delete(p)
    flash("U fshinë %d produkte. Porositë ekzistuese nuk u prekën." % n, "success")
    return redirect(url_for("admin.products"))


def _export_catalog():
    con = get_db()
    rows = con.execute("""SELECT p.*, c.name_sq cat, s.name_sq sub FROM products p JOIN categories c ON c.id=p.category_id
                          LEFT JOIN categories s ON s.id=p.subcategory_id ORDER BY p.id""")
    return _csv("katalogu.csv", csv_import.COLUMNS,
                [[r["sku"], r["name_sq"], r["name_en"], r["cat"], r["sub"] or "", r["brand"], r["packaging"], r["price"], r["discount_pct"],
                  r["stock"], r["visible"], ""] for r in rows])


# ---------------- product form ----------------

@bp.get("/produktet/re")
@auth.requires("products")
def product_new():
    return _form(None, {"visible": 1, "on_offers": 1, "low_threshold": 5, "stock": 0, "discount_pct": 0, "unit": "copë"}, {})


@bp.get("/produktet/<int:pid>")
@auth.requires("products")
def product_edit(pid):
    r = get_db().execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone() or abort(404)
    return _form(r, dict(r), {})


def _form(row, d, errors, status=200):
    con = get_db()
    imgs = con.execute("SELECT * FROM product_images WHERE product_id=? ORDER BY sort, id", (row["id"],)).fetchall() if row else []
    preview = None
    if row:
        from ..services.catalog import get_product
        preview = get_product(row["id"], public=False)
    subs = con.execute("SELECT id, name_sq FROM categories WHERE parent_id=? ORDER BY sort, name_sq", (d.get("category_id") or 0,)).fetchall()
    all_subs = {}
    for r in con.execute("SELECT id, name_sq, parent_id FROM categories WHERE parent_id IS NOT NULL ORDER BY sort, name_sq"):
        all_subs.setdefault(r["parent_id"], []).append([r["id"], r["name_sq"]])
    upd = None
    if row:
        upd = con.execute("SELECT * FROM audit_log WHERE area='products' AND object LIKE ? ORDER BY id DESC LIMIT 1", ("%" + row["sku"] + "%",)).fetchone()
    title = "Ndrysho produktin" if row else "Shto produkt"
    return page("admin/product_form.html", "prod", title, "Paneli › Produktet › " + (row["name_sq"] if row else "I ri"), row=row, d=d, errors=errors,
                imgs=imgs, cat_opts=[(c["pk"], c["name_sq"]) for c in categories(include_hidden=True)], subs=subs, all_subs=json.dumps(all_subs), preview=preview, discounts=DISCOUNTS,
                last_update=upd), status


@bp.post("/produktet/re")
@bp.post("/produktet/<int:pid>")
@auth.requires("products")
def product_save(pid=None):
    con = get_db()
    row = con.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone() if pid else None
    if pid and not row:
        abort(404)
    d, errors = psvc.validate(request.form, pid, con)
    uploads = [f for f in request.files.getlist("photos") if f and f.filename]
    have = con.execute("SELECT COUNT(*) FROM product_images WHERE product_id=?", (pid or 0,)).fetchone()[0]
    remove = [int(x) for x in request.form.getlist("remove_img") if x.isdigit()]
    if have - len(remove) + len(uploads) > 6:
        errors["photos"] = "Maksimumi 6 foto për produkt."
    saved = []
    if not errors:
        try:
            for f in uploads:
                saved.append(images.save_product_image(f))
        except images.ImageError as e:
            errors["photos"] = str(e)
            for s in saved:
                images.delete(s)
            saved = []
    if errors:
        merged = dict(row) if row else {}
        merged.update({k: v for k, v in d.items() if v is not None})
        return _form(row, merged, errors, 422)
    with transaction(con):
        if row:
            psvc.update(pid, d, con)
            if row["discount_pct"] != d["discount_pct"]:
                audit.log("Vendosi zbritje", "%s (%s)" % (d["name_sq"], d["sku"]), "%d%%" % row["discount_pct"], "%d%%" % d["discount_pct"], area="products", tone="new", con=con)
            changes = [k for k in ("name_sq", "price", "stock", "visible", "category_id") if str(row[k]) != str(d[k])]
            audit.log("Ndryshoi produkt", "%s (%s)" % (d["name_sq"], d["sku"]), "", ", ".join(changes), area="products", con=con)
        else:
            pid = psvc.insert(d, con)
            audit.log("Shtoi produkt", "%s (%s)" % (d["name_sq"], d["sku"]), area="products", tone="new", con=con)
        old_paths = []
        for iid in remove:
            r = con.execute("SELECT path FROM product_images WHERE id=? AND product_id=?", (iid, pid)).fetchone()
            if r:
                old_paths.append(r["path"])
                con.execute("DELETE FROM product_images WHERE id=?", (iid,))
        main = request.form.get("main_img", type=int)
        n = con.execute("SELECT COALESCE(MAX(sort), -1) FROM product_images WHERE product_id=?", (pid,)).fetchone()[0] + 1
        for s in saved:
            con.execute("INSERT INTO product_images(product_id, path, sort) VALUES (?,?,?)", (pid, s, n)); n += 1
        if main:
            con.execute("UPDATE product_images SET sort = CASE WHEN id=? THEN -1 ELSE sort END WHERE product_id=?", (main, pid))
    for p in old_paths:
        images.delete(p)
    flash("Produkti u ruajt.", "success")
    return redirect(url_for("admin.product_edit", pid=pid))


# ---------------- categories ----------------

@bp.get("/kategorite")
@auth.requires("categories")
def categories_admin():
    con = get_db()
    tree = categories(include_hidden=True)
    edit_id = request.args.get("ndrysho", type=int)
    new = request.args.get("re") is not None
    edit = con.execute("SELECT * FROM categories WHERE id=?", (edit_id,)).fetchone() if edit_id else None
    if not edit and not new and tree:
        edit = con.execute("SELECT * FROM categories WHERE id=?", (tree[0]["pk"],)).fetchone()
    counts = {r[0]: r[1] for r in con.execute("SELECT category_id, COUNT(*) FROM products GROUP BY category_id")}
    counts.update({r[0]: r[1] for r in con.execute("SELECT subcategory_id, COUNT(*) FROM products WHERE subcategory_id IS NOT NULL GROUP BY subcategory_id")})
    expand = request.args.get("hap", type=int) or (edit["parent_id"] or edit["id"] if edit else None)
    return page("admin/categories.html", "cats", "Kategoritë", "Paneli › Menaxhimi", tree=tree, edit=None if new else edit, counts=counts,
                expand=expand, errors={}, form={}, parent_opts=_parent_opts(tree, edit))


def _parent_opts(tree, edit):
    return [(c["pk"], c["name_sq"]) for c in tree if not edit or c["pk"] != edit["id"]]


@bp.post("/kategorite")
@auth.requires("categories")
def category_save():
    con = get_db()
    f = request.form
    cid = f.get("id", type=int)
    row = con.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone() if cid else None
    name, name_en = (f.get("name_sq") or "").strip()[:80], (f.get("name_en") or "").strip()[:80]
    parent = f.get("parent_id", type=int) or None
    errors = {}
    if len(name) < 2:
        errors["name_sq"] = "Shkruani emrin."
    if parent:
        p = con.execute("SELECT * FROM categories WHERE id=?", (parent,)).fetchone()
        if not p or p["parent_id"] is not None or parent == cid:
            errors["parent_id"] = "Prindi duhet të jetë një kategori kryesore (jo vetvetja)."
        elif row and con.execute("SELECT 1 FROM categories WHERE parent_id=?", (cid,)).fetchone():
            errors["parent_id"] = "Kjo kategori ka nënkategori — nuk mund të bëhet nënkategori."
    try:
        sort = int(f.get("sort") or 0)
    except ValueError:
        errors["sort"] = "Numër i plotë."
        sort = 0
    img = None
    fobj = request.files.get("image")
    if not errors and fobj and fobj.filename:
        try:
            img = images.save_category_image(fobj)
        except images.ImageError as e:
            errors["image"] = str(e)
    if errors:
        return page("admin/categories.html", "cats", "Kategoritë", "Paneli › Menaxhimi", tree=categories(include_hidden=True), edit=row, counts={},
                    expand=parent or cid, errors=errors, form=f, parent_opts=_parent_opts(categories(include_hidden=True), row)), 422
    t = now_iso()
    with transaction(con):
        vis, adult = 1 if f.get("visible") == "1" else 0, 1 if f.get("adult") == "1" else 0
        if row:
            con.execute("UPDATE categories SET name_sq=?, name_en=?, parent_id=?, sort=?, visible=?, adult=?, updated_at=? WHERE id=?",
                        (name, name_en, parent, sort, vis, adult, t, cid))
            if img:
                old = row["image"]
                con.execute("UPDATE categories SET image=? WHERE id=?", (img, cid))
                images.delete(old)
            if row["name_sq"] != name:
                psvc.recompute_search(con, cid)
            audit.log("Ndryshoi kategori", name, area="categories", con=con)
        else:
            pslug = con.execute("SELECT slug FROM categories WHERE id=?", (parent,)).fetchone()[0] if parent else None
            cur = con.execute("INSERT INTO categories(slug, name_sq, name_en, parent_id, image, sort, visible, adult, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (psvc.unique_slug(name, con, parent_slug=pslug), name, name_en, parent, img or "", sort, vis, adult, t, t))
            cid = cur.lastrowid
            audit.log("Krijoi kategori", name, area="categories", tone="new", con=con)
    flash("Kategoria u ruajt.", "success")
    return redirect(url_for("admin.categories_admin", ndrysho=cid))


@bp.post("/kategorite/<int:cid>/fshi")
@auth.requires("categories")
def category_delete(cid):
    con = get_db()
    row = con.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone() or abort(404)
    n = con.execute("SELECT COUNT(*) FROM products WHERE category_id=? OR subcategory_id=?", (cid, cid)).fetchone()[0]
    subs = con.execute("SELECT COUNT(*) FROM categories WHERE parent_id=?", (cid,)).fetchone()[0]
    if n or subs:
        flash("Kategoria ka %d produkte dhe %d nënkategori — zhvendosini ose fshini ato më parë." % (n, subs), "error")
        return redirect(url_for("admin.categories_admin", ndrysho=cid))
    with transaction(con):
        con.execute("DELETE FROM categories WHERE id=?", (cid,))
        audit.log("Fshiu kategori", row["name_sq"], area="categories", tone="danger", con=con)
    images.delete(row["image"])
    flash("Kategoria u fshi.", "success")
    return redirect(url_for("admin.categories_admin"))


@bp.post("/kategorite/<int:cid>/dukshme")
@auth.requires("categories")
def category_visible(cid):
    con = get_db()
    row = con.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone() or abort(404)
    con.execute("UPDATE categories SET visible=?, updated_at=? WHERE id=?", (0 if row["visible"] else 1, now_iso(), cid))
    audit.log("Shfaqi kategori" if not row["visible"] else "Fshehu kategori", row["name_sq"], area="categories", con=con)
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True)
    return redirect(request.referrer or url_for("admin.categories_admin"))


@bp.post("/kategorite/renditja")
@auth.requires("categories")
def category_order():
    con = get_db()
    ids = [int(x) for x in request.form.getlist("order") if x.isdigit()]
    with transaction(con):
        for i, cid in enumerate(ids, 1):
            con.execute("UPDATE categories SET sort=? WHERE id=?", (i, cid))
        audit.log("Ndryshoi renditjen e kategorive", "%d kategori" % len(ids), area="categories", con=con)
    return jsonify(ok=True)


# ---------------- CSV import ----------------

@bp.get("/produktet/importi")
@auth.requires("import")
def import_upload():
    return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="upload", error=None)


@bp.get("/produktet/importi/shablloni.csv")
@auth.requires("import")
def import_template():
    return Response(csv_import.TEMPLATE, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=shablloni-produkte.csv"})


@bp.post("/produktet/importi")
@auth.requires("import")
def import_parse():
    f = request.files.get("file")
    if not f or not f.filename:
        return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="upload", error="Zgjidhni një skedar CSV."), 400
    if not f.filename.lower().endswith((".csv", ".txt")):
        return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="upload", error="Lejohen vetëm skedarë .csv."), 400
    raw = f.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="upload", error="Skedari kalon 20 MB."), 413
    auto = request.form.get("auto_categories") == "1"
    try:
        rows, _d = csv_import.parse(raw, auto)
    except csv_import.ImportError_ as e:
        return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="upload", error=str(e)), 400
    jid = csv_import.save_job(f.filename, rows, auto, g.operator)
    return redirect(url_for("admin.import_preview", jid=jid))


def _job(jid):
    return get_db().execute("SELECT * FROM import_jobs WHERE id=?", (jid,)).fetchone() or abort(404)


@bp.get("/produktet/importi/<int:jid>")
@auth.requires("import")
def import_preview(jid):
    job = _job(jid)
    if job["status"] == "running":
        return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="progress", job=job)
    if job["status"] in ("done", "failed"):
        rows = csv_import.load_rows(job)
        return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="results", job=job,
                    errors=[r for r in rows if r["errors"]][:200])
    rows = csv_import.load_rows(job)
    s = csv_import.summary(rows)
    show = [r for r in rows if r["errors"] or r["warnings"]][:100] + [r for r in rows if not r["errors"] and not r["warnings"]][:30]
    show.sort(key=lambda r: r["line"])
    return page("admin/import.html", "prod", "Importo produkte nga CSV", "Paneli › Produktet › Importi", step="preview", job=job, s=s, rows=show)


@bp.post("/produktet/importi/<int:jid>/nis")
@auth.requires("import")
def import_run(jid):
    _job(jid)
    csv_import.start(jid, {"id": g.operator["id"], "name": g.operator["name"]})
    return redirect(url_for("admin.import_preview", jid=jid))


@bp.post("/produktet/importi/<int:jid>/anulo")
@auth.requires("import")
def import_discard(jid):
    get_db().execute("UPDATE import_jobs SET status='discarded' WHERE id=? AND status='preview'", (jid,))
    return redirect(url_for("admin.import_upload"))


@bp.get("/produktet/importi/<int:jid>/statusi")
@auth.requires("import")
def import_status(jid):
    j = _job(jid)
    return jsonify(status=j["status"], done=j["done_rows"], total=j["total"] - j["errors"], created=j["created_n"], updated=j["updated_n"])


@bp.get("/produktet/importi/<int:jid>/gabimet.csv")
@auth.requires("import")
def import_errors(jid):
    j = _job(jid)
    if not j["error_csv_path"]:
        abort(404)
    return send_file(Path(current_app.config["PRIVATE_DIR"]) / "imports" / j["error_csv_path"], as_attachment=True,
                     download_name="gabimet-importi-%d.csv" % jid, mimetype="text/csv")
