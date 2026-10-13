"""Attack-style tests: SQL injection / XSS payloads on every input, files that must never be
served, secret admin path, bot traps, admin sessions, backups, e-mail groups."""
import io
import re
import time
import zipfile

import pytest

from conftest import CHECKOUT, OWNER_PW, add_to_cart, checkout, csrf, login

SQLI = ["' OR '1'='1", "' OR 1=1 --", "\"; DROP TABLE products; --", "1; DELETE FROM orders", "') UNION SELECT password_hash FROM operators --",
        "%' AND 1=0 UNION SELECT sql FROM sqlite_master --", "1 OR 1=1", "admin'--", "\\'; DROP TABLE subscribers; --", "*", "\"*", "NEAR(", "%", "_"]
XSS = "<script>alert('x')</script><img src=x onerror=alert(1)>"


def _db():
    from enesai.db import get_db
    return get_db()


def _snapshot(app):
    with app.app_context():
        con = _db()
        tables = sorted(r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        counts = {t: con.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                  for t in ("products", "categories", "operators", "orders", "subscribers", "coupons")}
        pw = con.execute("SELECT password_hash FROM operators").fetchall()
        return tables, counts, [r[0] for r in pw]


def _clean(r):
    body = r.get_data(as_text=True)
    assert r.status_code < 500, (r.status_code, body[:300])
    for leak in ("Traceback", "sqlite3.", "OperationalError", "syntax error", "scrypt:", "pbkdf2:"):
        assert leak not in body, leak


def test_sql_injection_public_inputs_change_nothing(client, app):
    before = _snapshot(app)
    for p in SQLI:
        for url, params in (("/dyqani", {"q": p}), ("/dyqani", {"rendit": p, "cmimi_min": p, "cmimi_max": p, "faqe": p, "kategoria": p}),
                            ("/api/kerko", {"q": p}), ("/oferta", {"q": p}), ("/njoftime", {"faqe": p})):
            _clean(client.get(url, query_string=params))
        for url in ("/kategoria/" + p, "/produkt/" + p, "/porosia/" + p, "/njoftime/" + p, "/cabonohu/" + p):
            _clean(client.get(url))
        tok = csrf(client)
        _clean(client.post("/abonohu", data={"csrf_token": tok, "email": p + "@x.com"}))
        _clean(client.post("/api/kupon/kontrollo", data={"csrf_token": tok, "code": p}, headers={"X-CSRF-Token": tok}))
        _clean(client.post("/shporta/shto", data={"csrf_token": tok, "product": p, "qty": p}))
        _clean(client.post("/paneli-test/login", data={"csrf_token": csrf(client, "/paneli-test/login"), "username": p, "password": p}))
    assert _snapshot(app) == before


def test_sql_injection_checkout_and_admin_searches(client, app):
    add_to_cart(client)
    before_tables = _snapshot(app)[0]
    for p in SQLI[:6]:
        r, _i, _t = checkout(client, name=p, surname=p, address=p + " rruga 1", note=p, zone=p, coupon=p, email="")
        _clean(r)
    login(client)
    for p in SQLI:
        for url, params in (("/paneli-test/produktet", {"q": p, "rendit": p, "stoku": p, "kategoria": p}), ("/paneli-test/porosite", {"q": p, "statusi": p}),
                            ("/paneli-test/faturat", {"q": p}), ("/paneli-test/abonentet", {"q": p}), ("/paneli-test/kuponat", {"q": p}),
                            ("/paneli-test/regjistri", {"q": p})):
            _clean(client.get(url, query_string=params))
    tables, counts, pw = _snapshot(app)
    assert tables == before_tables and counts["products"] > 0 and len(pw) == 1


def test_xss_is_escaped_in_order_confirmation_and_admin(client, app):
    add_to_cart(client)
    r, _i, _t = checkout(client, name=XSS, surname="Test", address="Rr. " + XSS, note=XSS)
    assert r.status_code == 302
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "<script>alert" not in page and "<img src=x" not in page and "&lt;script&gt;" in page
    login(client)
    with app.app_context():
        nr = _db().execute("SELECT nr FROM orders ORDER BY id DESC LIMIT 1").fetchone()[0]
    drawer = client.get("/paneli-test/porosite/%s/drawer" % nr, headers={"X-Requested-With": "fetch"}).get_data(as_text=True)
    assert "<script>alert" not in drawer and "<img src=x" not in drawer and "&lt;script&gt;" in drawer


@pytest.mark.parametrize("path", ["/.env", "/.env.example", "/.git/config", "/instance/enesai.sqlite3", "/enesai.sqlite3", "/instance/secret_key",
                                  "/instance/admin_path", "/static/../.env", "/static/..%2f..%2f.env", "/static/%2e%2e/%2e%2e/.env",
                                  "/media/../secret_key", "/media/..%2fsecret_key", "/media/..%2f..%2f.env", "/media/private/invoices/x.pdf",
                                  "/run.py", "/requirements.txt", "/enesai/config.py", "/seed.py", "/instance/private/imports/job-1.json"])
def test_private_files_are_never_served(client, path):
    r = client.get(path)
    assert r.status_code in (400, 404), (path, r.status_code)
    body = r.get_data(as_text=True)
    assert "SECRET_KEY" not in body and "test-secret-key" not in body and "SQLite format" not in body


def test_secret_admin_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ENESAI_INSTANCE", str(tmp_path / "i"))
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.delenv("ADMIN_PATH", raising=False)
    from enesai import create_app
    app = create_app(TESTING=True)
    path = app.config["ADMIN_PATH"]
    assert re.match(r"^/paneli-[a-z0-9]{16}$", path)
    c = app.test_client()
    for guess in ("/admin", "/admin/login", "/paneli", "/paneli/login", "/administrator", "/wp-admin", "/login", "/dashboard", "/panel"):
        assert c.get(guess).status_code == 404, guess
    assert c.get(path + "/login").status_code == 200
    assert c.get(path + "/login").headers.get("X-Robots-Tag", "").startswith("noindex")
    robots = c.get("/robots.txt").get_data(as_text=True)
    assert path not in robots and "paneli" not in robots
    assert path not in c.get("/").get_data(as_text=True)
    assert create_app(TESTING=True).config["ADMIN_PATH"] == path   # stable across restarts


def test_honeypot_newsletter_and_checkout(client, app):
    tok = csrf(client)
    r = client.post("/abonohu", data={"csrf_token": tok, "email": "bot@spam.com", "website": "http://spam"}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    add_to_cart(client)
    r, _i, _t = checkout(client, website="http://spam")
    assert r.status_code == 422
    with app.app_context():
        assert not _db().execute("SELECT 1 FROM subscribers WHERE email='bot@spam.com'").fetchone()
        assert not _db().execute("SELECT 1 FROM orders WHERE is_demo=0").fetchone()


def test_checkout_too_fast_is_refused(client, app):
    app.config["CHECKOUT_MIN_SECONDS"] = 3
    add_to_cart(client)
    r, _i, _t = checkout(client)
    assert r.status_code == 422
    with client.session_transaction() as s:
        s["co_t"] = int(time.time()) - 10
    r, _i, _t = checkout(client)
    assert r.status_code in (302, 422)


def test_admin_session_bound_to_browser_and_max_age(client, app):
    login(client)
    assert client.get("/paneli-test/").status_code == 200
    assert client.get("/paneli-test/", headers={"User-Agent": "curl/8"}).status_code == 302      # copied cookie, other browser
    assert client.get("/paneli-test/").status_code == 302                                        # and the session is gone
    login(client)
    with app.app_context():
        _db().execute("UPDATE admin_sessions SET created_at='2020-01-01T00:00:00', last_seen=?", (time.strftime("%Y-%m-%dT%H:%M:%S"),))
    assert client.get("/paneli-test/").status_code == 302


@pytest.mark.parametrize("pw", ["Enesai2026!!", "Admin-12345678", "123456789abc", "Qwerty-2026-x", "aaaaaaaa111b", "Shkurt1!"])
def test_weak_passwords_refused(app, pw):
    with app.app_context():
        from enesai.services.auth import password_problem
        assert password_problem(pw, "pronari")


def test_backup_zip_contains_a_working_database(app):
    with app.app_context():
        from enesai.services.backup import backups, make_backup
        z = make_backup(app)
        assert z in backups(app)
        with zipfile.ZipFile(z) as zz:
            assert "enesai.sqlite3" in zz.namelist()
            import sqlite3, tempfile, os
            d = tempfile.mkdtemp(); zz.extract("enesai.sqlite3", d)
            con = sqlite3.connect(os.path.join(d, "enesai.sqlite3"))
            assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0
            con.close()


def test_email_groups_and_optin_only(client, app):
    add_to_cart(client)
    r, _i, _t = checkout(client, email="pa-pelqim@test.al")
    add_to_cart(client)
    r, _i, _t = checkout(client, email="me-pelqim@test.al", optin="1")
    with app.app_context():
        emails = [r[0] for r in _db().execute("SELECT email FROM subscribers")]
        assert "me-pelqim@test.al" in emails and "pa-pelqim@test.al" not in emails
    from enesai.admin.views_marketing import GROUP_MAX, MAILTO_MAX, _send_groups
    many = ["klient.nr%03d@gmail.com" % i for i in range(120)]
    groups, too_long = _send_groups(many, "Ofertat e javës", "Tekst i shkurtër\n• Qumësht — 150 L", "info@enesai.al")
    assert not too_long and sum(g["count"] for g in groups) == 120
    assert all(len(g["mailto"]) <= MAILTO_MAX and g["count"] <= GROUP_MAX for g in groups)
    assert "bcc=" in groups[0]["gmail"] and "klient.nr000%40gmail.com" in groups[0]["mailto"]
    _g, too_long = _send_groups(many, "x", "y" * 3000, "")
    assert too_long


def test_guessable_admin_path_in_env_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("ENESAI_INSTANCE", str(tmp_path / "j"))
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.setenv("ADMIN_PATH", "paneli")   # value shipped in older .env files
    from enesai import create_app
    app = create_app(TESTING=True)
    assert app.config["ADMIN_PATH"].startswith("/paneli-") and len(app.config["ADMIN_PATH"]) > 20
    assert app.test_client().get("/paneli/login").status_code == 404
