"""Announcements / ads / job posts (Reklamat & Njoftimet)."""
from ..db import get_db
from ..i18n import _, lang
from ..util import fmt_date, now_iso
from .catalog import media_url

TYPES = {
    "njoftim": ("info", "Njoftim", "Lexo njoftimin"),
    "reklame": ("new", "Reklamë", "Shiko më shumë"),
    "pune": ("success", "Shpallje pune", "Detajet e punës"),
}
TYPE_FROM_LABEL = {"Njoftim": "njoftim", "Reklamë": "reklame", "Shpallje pune": "pune"}

ACTIVE_SQL = "published = 1 AND (starts_at IS NULL OR starts_at = '' OR starts_at <= ?) AND (ends_at IS NULL OR ends_at = '' OR ends_at >= ?)"


def view(r):
    en = lang() == "en"
    tone, label, link_label = TYPES[r["type"]]
    return {
        "id": r["id"], "key": "%s:%s" % (r["id"], r["updated_at"]), "type": r["type"], "tone": tone,
        "type_label": _(label), "title": (r["title_en"] if en and r["title_en"] else r["title_sq"]),
        "text": (r["summary_en"] if en and r["summary_en"] else r["summary_sq"]),
        "body": (r["body_en"] if en and r["body_en"] else r["body_sq"]),
        "img": media_url(r["image"]) or "/static/img/photography/storefront-night.jpg", "contain": bool(r["image_contain"]),
        "href": r["link"] or "/njoftime",  # C-40: admin link when set, otherwise the list
        "detail_href": "/njoftime/%d" % r["id"],
        "link_label": _(r["link_label"] or link_label), "date": fmt_date(r["starts_at"] or r["created_at"]),
        "job_position": r["job_position"], "job_schedule": r["job_schedule"], "job_place": r["job_place"],
        "job_deadline": r["job_deadline"], "row": r,
    }


def home_announcements(limit=4):
    t = now_iso()
    rows = get_db().execute("SELECT * FROM announcements WHERE on_home = 1 AND " + ACTIVE_SQL + " ORDER BY sort, id DESC LIMIT ?",
                            (t, t, limit)).fetchall()
    return [view(r) for r in rows]


def public_list(type_=None, page=1, per_page=12):
    t = now_iso()
    where, args = ACTIVE_SQL, [t, t]
    counts = {k: 0 for k in TYPES}
    for r in get_db().execute("SELECT type, COUNT(*) n FROM announcements WHERE " + ACTIVE_SQL + " GROUP BY type", (t, t)):
        counts[r["type"]] = r["n"]
    if type_ in TYPES:
        where += " AND type = ?"
        args.append(type_)
    total = get_db().execute("SELECT COUNT(*) FROM announcements WHERE " + where, args).fetchone()[0]
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    rows = get_db().execute("SELECT * FROM announcements WHERE " + where + " ORDER BY COALESCE(NULLIF(starts_at,''), created_at) DESC, id DESC LIMIT ? OFFSET ?",
                            args + [per_page, (page - 1) * per_page]).fetchall()
    return {"items": [view(r) for r in rows], "counts": counts, "all": sum(counts.values()), "page": page, "pages": pages}


def get_public(aid):
    t = now_iso()
    r = get_db().execute("SELECT * FROM announcements WHERE id = ? AND " + ACTIVE_SQL, (aid, t, t)).fetchone()
    return view(r) if r else None
