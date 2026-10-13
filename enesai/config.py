"""Configuration from environment variables (see .env.example). No secrets in code."""
import os
import re
import secrets
import string
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "po")


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def load_dotenv(path):
    """Minimal .env reader (KEY=VALUE lines). Existing environment wins."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


GUESSABLE_ADMIN_PATHS = {"admin", "paneli", "panel", "administrator", "login", "dashboard", "wp-admin", "backend", "menaxhim", "staff"}


def _admin_path(inst):
    """The admin panel lives at a secret, random path (C-31 + client request): typing
    /admin or /paneli after the domain only shows the normal 404 page.
    ADMIN_PATH in .env wins; otherwise a random path is created once and kept in
    instance/admin_path (outside git, never served)."""
    env = os.environ.get("ADMIN_PATH", "").strip().strip("/")
    if env.lower() in GUESSABLE_ADMIN_PATHS:
        env = ""   # e.g. ADMIN_PATH=paneli from an older .env: never allow an easy-to-guess address
    if env:
        if not re.match(r"^[A-Za-z0-9._~-]{1,64}$", env):
            raise RuntimeError("ADMIN_PATH: vetëm shkronja, shifra, “-”, “_”, “.”, “~” (pa “/”).")
        return "/" + env
    inst.mkdir(parents=True, exist_ok=True)
    f = inst / "admin_path"
    if not f.exists():
        alphabet = string.ascii_lowercase + string.digits
        f.write_text("paneli-" + "".join(secrets.choice(alphabet) for _ in range(16)))
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return "/" + f.read_text().strip().strip("/")


class Config:
    def __init__(self, **overrides):
        load_dotenv(BASE_DIR / ".env")
        inst = Path(os.environ.get("ENESAI_INSTANCE", BASE_DIR / "instance"))
        self.INSTANCE_DIR = inst
        self.DATABASE = os.environ.get("ENESAI_DATABASE", str(inst / "enesai.sqlite3"))
        self.UPLOAD_DIR = inst / "uploads"
        self.PRIVATE_DIR = inst / "private"
        self.ENV = os.environ.get("ENESAI_ENV", "development")
        secret = os.environ.get("SECRET_KEY")
        if not secret and self.ENV == "production":
            raise RuntimeError("SECRET_KEY must be set in production (see .env.example)")
        if not secret:
            # Development fallback: a per-instance random key persisted outside git.
            inst.mkdir(parents=True, exist_ok=True)
            kf = inst / "secret_key"
            if not kf.exists():
                kf.write_text(secrets.token_hex(32))
                try:
                    os.chmod(kf, 0o600)
                except OSError:
                    pass
            secret = kf.read_text().strip()
        self.SECRET_KEY = secret
        self.HTTPS = _bool("ENESAI_HTTPS", self.ENV == "production")
        self.SESSION_COOKIE_NAME = "ea_s"
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = "Lax"
        self.SESSION_COOKIE_SECURE = self.HTTPS
        self.PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30  # cart keeps for 30 days
        self.MAX_CONTENT_LENGTH = 21 * 1024 * 1024  # CSV ≤ 20 MB
        self.ADMIN_PATH = _admin_path(inst)
        self.ADMIN_SESSION_MAX_HOURS = _int("ADMIN_SESSION_MAX_HOURS", 12)
        self.BACKUP_DIR = os.environ.get("BACKUP_DIR", str(inst / "backups"))
        self.BACKUP_KEEP_DAYS = _int("BACKUP_KEEP_DAYS", 30)
        self.CHECKOUT_MIN_SECONDS = _int("CHECKOUT_MIN_SECONDS", 3)   # bot trap: a person needs longer to fill the form
        self.LOGIN_MAX_FAILURES = _int("LOGIN_MAX_FAILURES", 6)
        self.LOGIN_LOCK_MINUTES = _int("LOGIN_LOCK_MINUTES", 15)
        self.MAX_QTY_PER_LINE = _int("MAX_QTY_PER_LINE", 20)
        self.COUPON_MAX_PCT = _int("COUPON_MAX_PCT", 90)
        self.ORDER_LINK_DAYS = _int("ORDER_LINK_DAYS", 30)
        self.MAX_DELIVERY_KM = _int("MAX_DELIVERY_KM", 60)
        self.ADULT_CHECKOUT_ENABLED = _bool("ADULT_CHECKOUT_ENABLED", False)
        self.MAP_TILE_URL = os.environ.get("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.MAP_TILE_ATTRIBUTION = os.environ.get("MAP_TILE_ATTRIBUTION", "© OpenStreetMap")
        self.WA_TOKEN = os.environ.get("WA_TOKEN", "")
        self.WA_PHONE_ID = os.environ.get("WA_PHONE_ID", "")
        self.WA_TEMPLATE = os.environ.get("WA_TEMPLATE", "")
        self.WA_TEMPLATE_LANG = os.environ.get("WA_TEMPLATE_LANG", "sq")
        self.WA_API_VERSION = os.environ.get("WA_API_VERSION", "v21.0")
        self.PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        self.TESTING = False
        for k, v in overrides.items():
            setattr(self, k, v)

    def as_dict(self):
        return {k: getattr(self, k) for k in dir(self) if k.isupper()}
