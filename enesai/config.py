"""Configuration from environment variables (see .env.example). No secrets in code."""
import os
import secrets
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
        self.ADMIN_PATH = "/" + os.environ.get("ADMIN_PATH", "paneli").strip("/")
        self.LOGIN_MAX_FAILURES = _int("LOGIN_MAX_FAILURES", 6)
        self.LOGIN_LOCK_MINUTES = _int("LOGIN_LOCK_MINUTES", 15)
        self.MAX_QTY_PER_LINE = _int("MAX_QTY_PER_LINE", 20)
        self.COUPON_MAX_PCT = _int("COUPON_MAX_PCT", 90)
        self.ORDER_LINK_DAYS = _int("ORDER_LINK_DAYS", 30)
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
