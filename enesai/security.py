"""CSRF, security headers (CSP), simple rate limiting, client IP."""
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from flask import abort, current_app, request, session

CSRF_KEY = "_csrf"


def csrf_token():
    t = session.get(CSRF_KEY)
    if not t:
        t = secrets.token_urlsafe(32)
        session[CSRF_KEY] = t
    return t


def check_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    good = session.get(CSRF_KEY) or ""
    if not good or not hmac.compare_digest(str(sent), str(good)):
        abort(400, description="csrf")


def client_ip():
    # Behind a reverse proxy configure ProxyFix (see DEPLOYMENT.md); never trust headers blindly.
    return request.remote_addr or ""


def security_headers(resp):
    cfg = current_app.config
    tile_hosts = _host_of(cfg.get("MAP_TILE_URL", ""))
    img_src = "'self' data: blob:" + ((" " + tile_hosts) if tile_hosts else "")
    csp = ("default-src 'self'; "
           "script-src 'self'; "
           "style-src 'self' 'unsafe-inline'; "  # the design uses inline style attributes
           "img-src " + img_src + "; "
           "font-src 'self'; "
           "connect-src 'self'; "
           "frame-src https://www.google.com https://maps.google.com; "
           "form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'")
    resp.headers.setdefault("Content-Security-Policy", csp)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=()")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    if cfg.get("HTTPS"):
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


def _host_of(url):
    if "://" not in url:
        return ""
    scheme, rest = url.split("://", 1)
    host = rest.split("/", 1)[0]
    if host.startswith("{s}."):
        host = "*." + host[4:]
    return scheme + "://" + host


class RateLimiter:
    """In-process sliding window. One process (Waitress) is the documented deployment;
    with several processes use a shared store (documented limitation)."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def hit(self, key, limit, window):
        if current_app.config.get("TESTING") and not current_app.config.get("RATE_LIMIT_IN_TESTS"):
            return True
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self.hits) > 50000:
                self.hits.clear()
            return True


limiter = RateLimiter()


def rate_limit(name, limit, window):
    if not limiter.hit(name + ":" + client_ip(), limit, window):
        abort(429)


# ---------------- bot traps (no CAPTCHA, no third parties) ----------------

def honeypot_tripped(data):
    """The hidden “website” field is never seen by people; scripts that fill every field do fill it."""
    return bool((data.get("website") or "").strip())


def bot_log(what):
    current_app.logger.warning("bot trap: %s from %s", what, client_ip())
