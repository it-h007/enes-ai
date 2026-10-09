"""CSV product import (V1-13, ADMIN_REQUIREMENTS §5).

Upload → parse (UTF-8 with/without BOM; fallback Windows-1252; delimiter , ; or TAB) →
per-row validation and preview (update / new / warning / error) → run in batches of 500
inside transactions in a background thread with progress → results + error CSV.
Rows match existing products by SKU (update) else create. Nothing is ever deleted.
foto_url is NOT downloaded (SSRF risk); only bundled /static/img/… paths are accepted."""
import csv
import io
import json
import re
import threading
from pathlib import Path

from flask import current_app

from ..db import connect, get_db
from ..util import csv_safe, norm, now_iso, slugify
from . import audit
from . import products as psvc
from .catalog import DISCOUNTS

COLUMNS = ["sku", "emri_sq", "emri_en", "kategoria", "nenkategoria", "marka", "paketimi", "cmimi", "zbritja", "stoku", "i_dukshem", "foto_url"]
ALIASES = {"emri": "emri_sq", "name": "emri_sq", "name_sq": "emri_sq", "name_en": "emri_en", "category": "kategoria", "subcategory": "nenkategoria",
           "nënkategoria": "nenkategoria", "brand": "marka", "pack": "paketimi", "packaging": "paketimi", "price": "cmimi", "çmimi": "cmimi",
           "discount": "zbritja", "stock": "stoku", "visible": "i_dukshem", "i_dukshëm": "i_dukshem", "image": "foto_url", "photo": "foto_url"}
MAX_ROWS = 200_000
BATCH = 500


class ImportError_(Exception):
    pass


def decode(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def sniff_delimiter(text):
    first = text.split("\n", 1)[0]
    counts = {d: first.count(d) for d in (",", ";", "\t")}
    d = max(counts, key=counts.get)
    return d if counts[d] else ","


def parse_price(v):
    s = str(v or "").strip().replace(" ", "").replace("L", "").replace("l", "")
    if re.match(r"^\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
    m = re.match(r"^(\d+)(?:[.,]0+)?$", s)
    if not m:
        return None
    n = int(m.group(1))
    return n if 0 < n <= 10_000_000 else None


def parse(raw, auto_categories=True, con=None):
    con = con or get_db()
    text = decode(raw)
    if not text.strip():
        raise ImportError_("Skedari është bosh.")
    delim = sniff_delimiter(text)
    rdr = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(rdr)
    except StopIteration:
        raise ImportError_("Skedari është bosh.")
    cols = [ALIASES.get(norm(h).replace(" ", "_"), norm(h).replace(" ", "_")) for h in header]
    missing = [c for c in ("sku", "emri_sq", "kategoria", "cmimi") if c not in cols]
    if missing:
        raise ImportError_("Mungojnë kolonat: %s. Shkarkoni shabllonin." % ", ".join(missing))
    cats = {}
    for r in con.execute("SELECT id, slug, name_sq, parent_id FROM categories"):
        cats[(r["parent_id"], norm(r["name_sq"]))] = r["id"]
        cats[(r["parent_id"], r["slug"])] = r["id"]
    existing = {r[0] for r in con.execute("SELECT sku FROM products")}
    rows, seen = [], set()
    for i, rec in enumerate(rdr, start=2):
        if i - 1 > MAX_ROWS:
            raise ImportError_("Shumë rreshta (maksimumi %d)." % MAX_ROWS)
        if not any(x.strip() for x in rec):
            continue
        d = {c: (rec[k].strip() if k < len(rec) else "") for k, c in enumerate(cols) if c in COLUMNS}
        errs, warns = [], []
        sku = d.get("sku", "")
        if not sku:
            errs.append(("Mungon SKU", "Shtoni një SKU unik dhe importoni sërish."))
        elif not psvc.SKU_RE.match(sku):
            errs.append(("SKU “%s” ka shenja të palejuara" % sku, "Përdorni shkronja, shifra, “-”, “_” ose “.”."))
        elif sku in seen:
            errs.append(("SKU “%s” përsëritet në skedar" % sku, "Mbani vetëm një rresht për çdo SKU."))
        seen.add(sku)
        if len(d.get("emri_sq", "")) < 2:
            errs.append(("Mungon emri", "Plotësoni kolonën emri_sq."))
        price = parse_price(d.get("cmimi"))
        if price is None:
            errs.append(("Çmimi “%s” nuk është numër" % d.get("cmimi", ""), "Përdorni vetëm shifra, p.sh. 250."))
        pct = 0
        if d.get("zbritja"):
            try:
                pct = int(d["zbritja"].replace("%", "").strip() or 0)
                if pct not in DISCOUNTS:
                    raise ValueError
            except ValueError:
                errs.append(("Zbritja “%s” nuk lejohet" % d["zbritja"], "Vlerat e lejuara: 0, 5, 10, 15, 20, 25, 30, 40, 50."))
        stock = 0
        if d.get("stoku", "") == "":
            warns.append("Stoku bosh → 0")
        else:
            try:
                stock = int(d["stoku"].replace(".", ""))
                if stock < 0:
                    raise ValueError
            except ValueError:
                errs.append(("Stoku “%s” nuk është numër" % d["stoku"], "Shkruani një numër të plotë ≥ 0."))
        vis = norm(d.get("i_dukshem", "1")) not in ("0", "jo", "false", "no", "n")
        cname = d.get("kategoria", "")
        cat_id = cats.get((None, norm(cname))) or cats.get((None, slugify(cname)))
        if not cname:
            errs.append(("Mungon kategoria", "Plotësoni kolonën kategoria."))
        elif not cat_id and not auto_categories:
            errs.append(("Kategoria “%s” nuk ekziston" % cname, "Krijojeni te Kategoritë ose aktivizoni krijimin automatik."))
        elif not cat_id:
            warns.append("Kategori e re: %s" % cname)
        sname = d.get("nenkategoria", "")
        if sname and cat_id and not cats.get((cat_id, norm(sname))):
            if auto_categories:
                warns.append("Nënkategori e re: %s" % sname)
            else:
                errs.append(("Nënkategoria “%s” nuk ekziston" % sname, "Krijojeni ose aktivizoni krijimin automatik."))
        foto = d.get("foto_url", "")
        if foto and not foto.startswith("/static/img/"):
            warns.append("foto_url nuk shkarkohet — ngarkoni foton te produkti")
            foto = ""
        rows.append({"line": i, "sku": sku, "name_sq": d.get("emri_sq", ""), "name_en": d.get("emri_en", ""), "cat": cname, "sub": sname,
                     "brand": d.get("marka", ""), "pack": d.get("paketimi", ""), "price": price, "pct": pct, "stock": stock, "visible": vis,
                     "foto": foto, "errors": errs, "warnings": warns, "kind": "error" if errs else ("update" if sku in existing else "new"),
                     "raw_price": d.get("cmimi", ""), "raw_stock": d.get("stoku", "")})
    return rows, delim


def summary(rows):
    return {"total": len(rows), "ok": sum(1 for r in rows if not r["errors"]), "warn": sum(1 for r in rows if r["warnings"] and not r["errors"]),
            "err": sum(1 for r in rows if r["errors"]), "new": sum(1 for r in rows if r["kind"] == "new"), "upd": sum(1 for r in rows if r["kind"] == "update")}


def save_job(filename, rows, auto_categories, operator):
    con = get_db()
    s = summary(rows)
    cur = con.execute("INSERT INTO import_jobs(filename, created_by, created_at, status, total, warnings, errors, auto_categories) VALUES (?,?,?, 'preview', ?,?,?,?)",
                      (filename[:120], operator["name"], now_iso(), s["total"], s["warn"], s["err"], 1 if auto_categories else 0))
    jid = cur.lastrowid
    path = Path(current_app.config["PRIVATE_DIR"]) / "imports" / ("job-%d.json" % jid)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    con.execute("UPDATE import_jobs SET payload_path=? WHERE id=?", (path.name, jid))
    return jid


def load_rows(job):
    return json.loads((Path(current_app.config["PRIVATE_DIR"]) / "imports" / job["payload_path"]).read_text(encoding="utf-8"))


def start(job_id, operator):
    app = current_app._get_current_object()
    con = get_db()
    cur = con.execute("UPDATE import_jobs SET status='running' WHERE id=? AND status='preview'", (job_id,))
    if cur.rowcount != 1:
        return False
    th = threading.Thread(target=_run, args=(app, job_id, operator), daemon=True)
    th.start()
    if app.config.get("TESTING"):
        th.join()
    return True


def _run(app, job_id, operator):
    with app.app_context():
        con = connect(app.config["DATABASE"])
        try:
            job = con.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
            rows = json.loads((Path(app.config["PRIVATE_DIR"]) / "imports" / job["payload_path"]).read_text(encoding="utf-8"))
            good = [r for r in rows if not r["errors"]]
            created = updated = done = 0
            for start_i in range(0, len(good), BATCH):
                chunk = good[start_i:start_i + BATCH]
                con.execute("BEGIN IMMEDIATE")
                try:
                    for r in chunk:
                        c, u = _apply(con, r, job["auto_categories"])
                        created += c; updated += u
                    con.execute("COMMIT")
                except Exception:
                    con.execute("ROLLBACK")
                    raise
                done += len(chunk)
                con.execute("UPDATE import_jobs SET done_rows=?, created_n=?, updated_n=? WHERE id=?", (done, created, updated, job_id))
            errs = [r for r in rows if r["errors"]]
            if errs:
                p = Path(app.config["PRIVATE_DIR"]) / "imports" / ("job-%d-gabimet.csv" % job_id)
                with p.open("w", encoding="utf-8-sig", newline="") as fh:
                    w = csv.writer(fh, delimiter=";")
                    w.writerow(["rreshti", "sku", "emri_sq", "problemi", "si_ta_rregulloni"])
                    for r in errs:
                        for prob, fix in r["errors"]:
                            w.writerow([r["line"], csv_safe(r["sku"]), csv_safe(r["name_sq"]), csv_safe(prob), csv_safe(fix)])
                con.execute("UPDATE import_jobs SET error_csv_path=? WHERE id=?", (p.name, job_id))
            con.execute("UPDATE import_jobs SET status='done', finished_at=? WHERE id=?", (now_iso(), job_id))
            audit.log("Importoi CSV", "%s · %d ok, %d gabime" % (job["filename"], created + updated, len(errs)),
                      "", "krijuar %d · përditësuar %d" % (created, updated), area="import", con=con, operator=operator)
        except Exception:  # pragma: no cover - logged, job marked failed
            app.logger.exception("import job %s failed", job_id)
            con.execute("UPDATE import_jobs SET status='failed', finished_at=? WHERE id=?", (now_iso(), job_id))
        finally:
            con.close()


def _category(con, name, parent_id, auto):
    nm = norm(name)
    for row in con.execute("SELECT id, name_sq, slug FROM categories WHERE parent_id IS ?", (parent_id,)):
        if norm(row["name_sq"]) == nm or row["slug"] == slugify(name):
            return row["id"]
    if not auto:
        return None
    parent_slug = con.execute("SELECT slug FROM categories WHERE id=?", (parent_id,)).fetchone()[0] if parent_id else None
    sort = (con.execute("SELECT COALESCE(MAX(sort),0) FROM categories WHERE parent_id IS ?", (parent_id,)).fetchone()[0] or 0) + 1
    t = now_iso()
    cur = con.execute("INSERT INTO categories(slug, name_sq, parent_id, sort, visible, created_at, updated_at) VALUES (?,?,?,?,1,?,?)",
                      (psvc.unique_slug(name, con, parent_slug=parent_slug), name.strip()[:80], parent_id, sort, t, t))
    return cur.lastrowid


def _apply(con, r, auto):
    cat = _category(con, r["cat"], None, auto)
    sub = _category(con, r["sub"], cat, auto) if r["sub"] and cat else None
    ex = con.execute("SELECT * FROM products WHERE sku=?", (r["sku"],)).fetchone()
    d = {"sku": r["sku"], "name_sq": r["name_sq"][:160], "name_en": (r["name_en"] or (ex["name_en"] if ex else ""))[:160],
         "desc_sq": ex["desc_sq"] if ex else "", "desc_en": ex["desc_en"] if ex else "", "brand": (r["brand"] or (ex["brand"] if ex else ""))[:80],
         "packaging": (r["pack"] or (ex["packaging"] if ex else ""))[:60], "unit": ex["unit"] if ex else "copë", "barcode": ex["barcode"] if ex else "",
         "price": r["price"], "discount_pct": r["pct"], "stock": r["stock"], "low_threshold": ex["low_threshold"] if ex else 5,
         "allow_backorder": ex["allow_backorder"] if ex else 0, "visible": 1 if r["visible"] else 0, "on_offers": ex["on_offers"] if ex else 1,
         "category_id": cat, "subcategory_id": sub}
    if ex:
        psvc.update(ex["id"], d, con)
        pid, c, u = ex["id"], 0, 1
    else:
        pid, c, u = psvc.insert(d, con), 1, 0
    if r.get("foto") and not con.execute("SELECT 1 FROM product_images WHERE product_id=?", (pid,)).fetchone():
        con.execute("INSERT INTO product_images(product_id, path, sort) VALUES (?,?,0)", (pid, r["foto"]))
    return c, u


TEMPLATE = "﻿" + ";".join(COLUMNS) + "\n" + "FR-1050;Avokado Hass;Hass avocado;Fruta & Perime;Fruta;Import · Spanjë;2 copë;300;20;30;1;\n"
