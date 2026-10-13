"""ENES’AI SUPER MARKET — Flask application factory."""
import logging
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, g, render_template, request, session
from markupsafe import Markup, escape

from . import db as dbm
from .config import Config
from .i18n import _, detect
from .security import check_csrf, csrf_token, security_headers
from .util import fmt_date, fmt_dt, fmt_time, icon, lek, maps_url, num, now

NAV = [
    ("home", "Ballina", "/"), ("shop", "Dyqani Online", "/dyqani"), ("offers", "Ofertat", "/oferta"),
    ("cats", "Kategoritë", "/kategorite"), ("about", "Rreth Nesh", "/rreth-nesh"),
    ("news", "Njoftime", "/njoftime"), ("contact", "Kontakt", "/kontakt"),
]


def _security_warnings(app):
    """Loud start-up warnings for risky production settings (nothing secret is logged)."""
    import os
    import stat
    from .config import BASE_DIR, GUESSABLE_ADMIN_PATHS
    if os.environ.get("ADMIN_PATH", "").strip().strip("/").lower() in GUESSABLE_ADMIN_PATHS:
        app.logger.warning("ADMIN_PATH në .env është e lehtë për t'u gjetur dhe u injorua — paneli është te rruga sekrete (python run.py admin-url).")
    env = BASE_DIR / ".env"
    if app.config.get("ENV") == "production" and env.exists() and os.name == "posix":
        if env.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            app.logger.warning(".env lexohet nga përdorues të tjerë të serverit — ekzekutoni: chmod 600 .env")


def create_app(**overrides):
    cfg = Config(**overrides)
    app = Flask(__name__, instance_path=str(cfg.INSTANCE_DIR), instance_relative_config=False)
    app.config.update(cfg.as_dict())
    for d in (cfg.INSTANCE_DIR, cfg.UPLOAD_DIR, cfg.PRIVATE_DIR, cfg.PRIVATE_DIR / "invoices", cfg.PRIVATE_DIR / "imports"):
        Path(d).mkdir(parents=True, exist_ok=True)

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.jinja_env.globals.update(icon=icon, _=_, csrf_token=csrf_token, lek=lek, num=num, maps_url=maps_url,
                                 page_window=page_window, NAV=NAV, qr_svg=_qr_svg)
    app.jinja_env.filters.update(lek=lek, date=fmt_date, time=fmt_time, dt=fmt_dt, num=num)

    _logging(app)
    _security_warnings(app)

    with app.app_context():
        con = dbm.connect(app.config["DATABASE"])
        dbm.migrate(con)
        con.close()

    app.teardown_appcontext(dbm.close_db)

    from .public import bp as public_bp
    from .api import bp as api_bp
    from .checkout import bp as checkout_bp
    app.register_blueprint(checkout_bp)
    from .admin import bp as admin_bp
    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp, url_prefix=app.config["ADMIN_PATH"])

    @app.before_request
    def _before():
        g.lang, explicit = detect()
        g.set_lang_cookie = explicit
        check_csrf()

    @app.after_request
    def _after(resp):
        if getattr(g, "set_lang_cookie", False):
            resp.set_cookie("ea_lang", g.lang, max_age=60 * 60 * 24 * 365, samesite="Lax",
                            secure=app.config["HTTPS"], httponly=True)
        if request.path.startswith(app.config["ADMIN_PATH"]) or request.path.startswith("/porosia/"):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return security_headers(resp)

    app.context_processor(_context)
    from .errors import register as register_errors
    register_errors(app)
    from .cli import register as register_cli
    register_cli(app)
    return app


def _qr_svg(text, cls="ea-qr"):
    from .services.qr import svg
    return svg(text, cls)


def _logging(app):
    if not app.logger.handlers or app.config["ENV"] == "production":
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app.logger.addHandler(h)
    app.logger.setLevel(logging.INFO)


def page_window(page, pages):
    """Page numbers with gaps, e.g. page 1 of 17 → 1 2 3 … 17 (as designed)."""
    if pages <= 7:
        return list(range(1, pages + 1))
    lo, hi = max(1, page - 1), min(pages, page + 1)
    if page == 1:
        hi = 3
    if page == pages:
        lo = pages - 2
    nums = sorted({1, pages} | set(range(lo, hi + 1)))
    out, prev = [], 0
    for n in nums:
        if n - prev > 1:
            out.append("…")
        out.append(n)
        prev = n
    return out


def _context():
    from flask import current_app
    from .services import cart as cartsvc
    from .services import settings as st
    from .services.catalog import categories, media_url
    s = st.all_settings()
    show_ph = current_app.config["ENV"] != "production"
    addr = s.get("address", "")
    q_maps = s.get("maps_link") or (maps_url(s["store_lat"], s["store_lng"]) if s.get("store_lat") and s.get("store_lng")
                                     else "https://maps.google.com/?q=" + "ENES%E2%80%99AI+Super+Market+Vlor%C3%AB")
    social = [(n, s.get(k)) for n, k in (("Facebook", "facebook"), ("Instagram", "instagram"), ("TikTok", "tiktok")) if s.get(k)]
    social_real = bool(social)
    if not social and show_ph:
        social = [("Facebook", "#"), ("Instagram", "#"), ("TikTok", "#")]
    from .util import clean_phone, e164_digits
    store = {
        "city": s.get("city") or "Vlorë", "delivery_area": s.get("delivery_area") or "Vlorë",
        "address": addr, "phone": s.get("phone", ""), "phone_href": clean_phone(s.get("phone", "")),
        "email": s.get("email", ""), "hours": st.hours_text(s), "whatsapp": s.get("whatsapp", ""),
        "whatsapp_digits": e164_digits(s.get("whatsapp", "")), "maps_url": q_maps,
        "social": social, "social_real": social_real, "trade": s.get("tradeName"), "short": s.get("short"),
        "legal": s.get("legalName", ""), "nipt": s.get("nipt", ""),
    }
    call = s.get("studio_call", "")
    wa = s.get("studio_wa", "")
    studio = {"call": call, "call_href": "tel:" + clean_phone(call), "wa": wa,
              "wa_href": "https://wa.me/" + e164_digits(wa) if wa else "#"}

    def show(key):
        return bool(store.get(key)) or show_ph

    def ph(key, label):
        v = store.get(key) if key in store else s.get(key, "")
        if v:
            return escape(v)
        if not show_ph:
            return ""
        return Markup('<span class="ea-ph" data-store="%s" title="%s">%s</span>') % (
            key, "Vendmbajtëse — plotësohet te Paneli › Cilësimet", label)

    def lang_url(code):
        args = request.args.to_dict(flat=True)
        args["lang"] = code
        return request.path + "?" + urlencode(args)

    def logo_src(variant=None):
        if variant == "light":
            return media_url(s.get("logo_light")) if s.get("logo_light") else "/static/img/logos/enesai-logo-light.svg"
        if variant == "mark":
            return "/static/img/logos/enesai-mark.svg"
        return media_url(s.get("logo_dark")) if s.get("logo_dark") else "/static/img/logos/enesai-logo-dark.svg"

    def static(path):
        v = _static_versions.get(path)
        if v is None:
            p = Path(current_app.static_folder) / path
            v = str(int(p.stat().st_mtime)) if p.exists() else "0"
            _static_versions[path] = v
        return "/static/" + path + "?v=" + v

    path = request.path if request else ""
    hide_cookie = path.startswith(("/arka", "/porosia")) or path.startswith(current_app.config["ADMIN_PATH"]) \
        or request.cookies.get("ea_cookie_ok")
    return {
        "lang": g.get("lang", "sq"), "nav": NAV, "store": store, "studio": studio, "settings": s,
        "show": show, "ph": ph, "show_ph": show_ph, "lang_url": lang_url, "logo_src": logo_src, "static": static,
        "cart_count": cartsvc.count() if not path.startswith(current_app.config["ADMIN_PATH"]) else 0,
        "all_categories": categories, "year": now().year, "show_cookie_notice": not hide_cookie,
        "admin_path": current_app.config["ADMIN_PATH"], "media_url": media_url,
    }


_static_versions = {}
