import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from enesai import create_app  # noqa: E402
from enesai.db import get_db  # noqa: E402

OWNER_PW = "Test-Pasw0rd-2026!"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("ENESAI_INSTANCE", str(tmp_path / "inst"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-production")
    monkeypatch.setenv("ADMIN_PATH", "paneli-test")  # fixed path for the tests; production uses a random one
    monkeypatch.delenv("WA_TOKEN", raising=False)
    app = create_app(TESTING=True, CHECKOUT_MIN_SECONDS=0)
    with app.app_context():
        import seed
        seed.seed(get_db())
        from enesai.services.auth import create_owner
        ok, msg = create_owner("pronari", "Pronari", OWNER_PW)
        assert ok, msg
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client, path="/"):
    r = client.get(path)
    m = re.search(r'name="csrf-token" content="([^"]+)"', r.text) or re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1)


def login(client, username="pronari", password=OWNER_PW):
    tok = csrf(client, "/paneli-test/login")
    return client.post("/paneli-test/login", data={"csrf_token": tok, "username": username, "password": password})


def make_operator(app, username, role="operator", perms=(), password="Operator-Pass-77"):
    with app.app_context():
        from enesai.services.auth import hash_password
        from enesai.util import now_iso
        con = get_db()
        oid = con.execute("INSERT INTO operators(name, username, password_hash, role, active, must_change_password, created_at) VALUES (?,?,?,?,1,0,?)",
                          (username.title(), username, hash_password(password), role, now_iso())).lastrowid
        for s in perms:
            con.execute("INSERT INTO operator_permissions(operator_id, section) VALUES (?,?)", (oid, s))
    return password


CHECKOUT = {"name": "Test", "surname": "Klient", "phone": "069 555 1234", "email": "", "zone": "Lungomare", "address": "Rr. Testi, Pall. 1",
            "note": "", "terms": "1", "pay": "cash", "lat": "40.453910", "lng": "19.483070", "loc_source": "map", "accuracy_m": ""}


def add_to_cart(client, pid=1050, qty=1):
    tok = csrf(client)
    r = client.post("/shporta/shto", data={"csrf_token": tok, "product": pid, "qty": qty}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200, r.text
    return r.get_json()


def checkout(client, **over):
    r = client.get("/arka")
    tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
    idem = re.search(r'name="idem" value="([^"]+)"', r.text).group(1)
    data = dict(CHECKOUT, csrf_token=tok, idem=idem, action="order")
    data.update(over)
    return client.post("/arka", data=data), idem, tok
