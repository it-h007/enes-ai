import io
import re

from PIL import Image

from conftest import OWNER_PW, csrf, login, make_operator


def _db():
    from enesai.db import get_db
    return get_db()


def test_admin_requires_login(client):
    for p in ("/paneli/", "/paneli/produktet", "/paneli/porosite", "/paneli/cilesimet", "/paneli/kuponat"):
        r = client.get(p)
        assert r.status_code == 302 and "/paneli/login" in r.headers["Location"]


def test_login_wrong_and_lockout(client, app):
    for i in range(app.config["LOGIN_MAX_FAILURES"]):
        r = login(client, password="gabim-%d" % i)
        assert r.status_code in (401, 429)
    r = login(client)  # correct password but locked now
    assert r.status_code == 429 and "bllokua" in r.text
    with app.app_context():
        assert _db().execute("SELECT COUNT(*) FROM audit_log WHERE action='Hyrje e dështuar'").fetchone()[0] >= 6
        logs = " ".join(r[0] + r[1] for r in _db().execute("SELECT object, after FROM audit_log"))
        assert "gabim-" not in logs and OWNER_PW not in logs  # never log passwords


def test_login_and_logout_revokes_session(client):
    assert login(client).status_code == 302
    assert client.get("/paneli/").status_code == 200
    client.post("/paneli/dil", data={"csrf_token": csrf(client, "/paneli/")})
    assert client.get("/paneli/").status_code == 302


def test_owner_bootstrap_only_once(app):
    with app.app_context():
        from enesai.services.auth import create_owner
        ok, _ = create_owner("tjeter", "Tjetër", "Shume-i-forte-2026")
        assert not ok


def test_operator_permissions_enforced_server_side(app):
    make_operator(app, "dritan", "operator", ["products", "coupons"])  # coupons must be ignored for operators
    c = app.test_client()
    login(c, "dritan", "Operator-Pass-77")
    assert c.get("/paneli/produktet").status_code == 200
    assert c.get("/paneli/porosite").status_code == 403
    assert c.get("/paneli/operatoret").status_code == 403
    assert c.get("/paneli/cilesimet").status_code == 403
    r = c.get("/paneli/kuponat")
    assert r.status_code == 403 and "Nuk keni leje" in r.text
    tok = csrf(c, "/paneli/produktet")
    assert c.post("/paneli/kuponat", data={"csrf_token": tok, "code": "HACK1", "pct": "50"}).status_code == 403
    assert c.post("/paneli/kuponat/VLORE10/anulo", data={"csrf_token": tok}).status_code == 403
    with app.app_context():
        assert not _db().execute("SELECT 1 FROM coupons WHERE code='HACK1'").fetchone()
        assert _db().execute("SELECT COUNT(*) FROM audit_log WHERE action='Akses i ndaluar'").fetchone()[0] >= 4


def test_manager_can_create_and_cancel_coupon(app):
    make_operator(app, "elira", "manager", ["coupons", "orders"])
    c = app.test_client()
    login(c, "elira", "Operator-Pass-77")
    tok = csrf(c, "/paneli/kuponat")
    r = c.post("/paneli/kuponat", data={"csrf_token": tok, "code": "verifikim25", "pct": "25", "action": "create"})
    assert r.status_code == 200 and "VERIFIKIM25" in r.text
    r = c.post("/paneli/kuponat", data={"csrf_token": tok, "code": "VERIFIKIM25", "pct": "25", "action": "create"})
    assert r.status_code == 422 and "ekziston" in r.text
    r = c.post("/paneli/kuponat", data={"csrf_token": tok, "code": "ab", "pct": "95", "action": "create"})
    assert r.status_code == 422
    c.post("/paneli/kuponat/VERIFIKIM25/anulo", data={"csrf_token": tok})
    with app.app_context():
        row = _db().execute("SELECT status, created_by_name FROM coupons WHERE code='VERIFIKIM25'").fetchone()
        assert row["status"] == "cancelled" and row["created_by_name"] == "Elira"


def test_owner_cannot_be_deleted_or_disabled(client, app):
    login(client)
    with app.app_context():
        oid = _db().execute("SELECT id FROM operators WHERE role='owner'").fetchone()[0]
    tok = csrf(client, "/paneli/operatoret")
    assert client.post("/paneli/operatoret/%d/fshi" % oid, data={"csrf_token": tok}).status_code == 403
    assert client.post("/paneli/operatoret/%d/aktiv" % oid, data={"csrf_token": tok}).status_code == 403


def test_operator_create_requires_password_change(client, app):
    login(client)
    tok = csrf(client, "/paneli/operatoret")
    r = client.post("/paneli/operatoret", data={"csrf_token": tok, "name": "Ana Lika", "username": "ana.l", "password": "Perkohshem-123",
                                                "role": "operator", "active": "1", "perms": ["orders", "coupons"]})
    assert r.status_code == 302
    with app.app_context():
        perms = {x[0] for x in _db().execute("SELECT section FROM operator_permissions p JOIN operators o ON o.id=p.operator_id WHERE o.username='ana.l'")}
        assert perms == {"orders"}
    c2 = app.test_client()
    login(c2, "ana.l", "Perkohshem-123")
    assert "/paneli/fjalekalimi" in c2.get("/paneli/porosite").headers["Location"]


def test_deactivated_operator_session_revoked(app):
    make_operator(app, "temp", "operator", ["orders"])
    c = app.test_client()
    login(c, "temp", "Operator-Pass-77")
    assert c.get("/paneli/porosite").status_code == 200
    owner = app.test_client()
    login(owner)
    with app.app_context():
        oid = _db().execute("SELECT id FROM operators WHERE username='temp'").fetchone()[0]
    owner.post("/paneli/operatoret/%d/aktiv" % oid, data={"csrf_token": csrf(owner, "/paneli/operatoret")})
    assert c.get("/paneli/porosite").status_code == 302


def test_product_crud_with_image_upload(client, app):
    login(client)
    tok = csrf(client, "/paneli/produktet/re")
    with app.app_context():
        cid = _db().execute("SELECT id FROM categories WHERE slug='bulmet'").fetchone()[0]
    buf = io.BytesIO()
    Image.new("RGB", (900, 900), (240, 200, 10)).save(buf, "PNG")
    buf.seek(0)
    r = client.post("/paneli/produktet/re", data={"csrf_token": tok, "name_sq": "Kos dele", "sku": "BU-9001", "price": "2.100", "discount_pct": "10",
                                                  "stock": "12", "low_threshold": "5", "visible": "1", "category_id": str(cid),
                                                  "photos": (buf, "kos.png")}, content_type="multipart/form-data")
    assert r.status_code == 302, r.text[:500]
    with app.app_context():
        p = _db().execute("SELECT * FROM products WHERE sku='BU-9001'").fetchone()
        assert p["price"] == 2100 and p["sale_price"] == 1890
        img = _db().execute("SELECT path FROM product_images WHERE product_id=?", (p["id"],)).fetchone()[0]
        assert img.startswith("products/") and img.endswith(".jpg")
    assert client.get("/media/" + img).status_code == 200
    assert "Kos dele" in client.get("/dyqani?q=kos").text


def test_upload_rejects_non_images_and_svg(client, app):
    login(client)
    tok = csrf(client, "/paneli/produktet/re")
    with app.app_context():
        cid = _db().execute("SELECT id FROM categories WHERE slug='bulmet'").fetchone()[0]
    data = {"csrf_token": tok, "name_sq": "Test", "sku": "T-1", "price": "100", "category_id": str(cid),
            "photos": (io.BytesIO(b"<svg onload=alert(1)></svg>"), "x.png")}
    r = client.post("/paneli/produktet/re", data=data, content_type="multipart/form-data")
    assert r.status_code == 422 and "foto e vlefshme" in r.text
    tok = csrf(client, "/paneli/cilesimet")
    r = client.post("/paneli/cilesimet", data={"csrf_token": tok, "logo_dark": (io.BytesIO(b"<svg/>"), "logo.svg")}, content_type="multipart/form-data")
    assert r.status_code == 200 and "SVG nuk pranohet" in r.text
    assert client.get("/media/../instance/secret_key").status_code == 404


def test_product_validation(client, app):
    login(client)
    tok = csrf(client, "/paneli/produktet/re")
    r = client.post("/paneli/produktet/re", data={"csrf_token": tok, "name_sq": "", "sku": "FR-1050", "price": "abc", "discount_pct": "33"})
    assert r.status_code == 422
    for msg in ("Shkruani emrin", "SKU ekziston", "Çmimi", "Zgjidhni kategorinë"):
        assert msg in r.text


def test_bulk_discount_and_audit(client, app):
    login(client)
    tok = csrf(client, "/paneli/produktet")
    client.post("/paneli/produktet/bulk", data={"csrf_token": tok, "action": "discount", "pct": "30", "ids": ["3011", "3002"]})
    with app.app_context():
        r = _db().execute("SELECT discount_pct, sale_price FROM products WHERE id=3011").fetchone()
        assert r["discount_pct"] == 30 and r["sale_price"] == 315
        assert _db().execute("SELECT COUNT(*) FROM audit_log WHERE action='Vendosi zbritje'").fetchone()[0] == 2


def test_delete_all_requires_typed_confirmation_and_owner(client, app):
    make_operator(app, "prod", "manager", ["products"])
    c = app.test_client()
    login(c, "prod", "Operator-Pass-77")
    assert c.post("/paneli/produktet/fshi-te-gjitha", data={"csrf_token": csrf(c, "/paneli/produktet"), "confirm": "FSHI TË GJITHA"}).status_code == 403
    login(client)
    tok = csrf(client, "/paneli/produktet")
    client.post("/paneli/produktet/fshi-te-gjitha", data={"csrf_token": tok, "confirm": "fshi"})
    with app.app_context():
        assert _db().execute("SELECT COUNT(*) FROM products").fetchone()[0] == 9
    client.post("/paneli/produktet/fshi-te-gjitha", data={"csrf_token": tok, "confirm": "FSHI TË GJITHA"})
    with app.app_context():
        assert _db().execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0


def _import(client, content, auto="1"):
    tok = csrf(client, "/paneli/produktet/importi")
    r = client.post("/paneli/produktet/importi", data={"csrf_token": tok, "auto_categories": auto, "file": (io.BytesIO(content), "p.csv")},
                    content_type="multipart/form-data")
    return r


def test_csv_import_bom_semicolon_update_and_errors(client, app):
    login(client)
    csv_text = ("﻿sku;emri_sq;emri_en;kategoria;nenkategoria;marka;paketimi;cmimi;zbritja;stoku;i_dukshem;foto_url\n"
                "FR-1050;Avokado Hass;;Fruta & Perime;Fruta;;2 copë;320;0;31;1;\n"
                "UB-5044;Oriz Basmati 1 kg;;Ushqime Bazë;;;1 kg;390;;48;1;https://evil.example/x.jpg\n"
                ";Kos dele;;Bulmet;;;;210;;20;1;\n"
                "SN-7003;Çokollatë;;Ëmbëlsirat;;;;2,5O;;15;1;\n"
                "PS-8020;Detergjent 3 L;;Kategori e Re;;;3 L;1.150;10;;1;\n").encode("utf-8")
    r = _import(client, csv_text)
    assert r.status_code == 302
    jid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    prev = client.get(r.headers["Location"]).text
    assert "Mungon SKU" in prev and "nuk është numër" in prev and "nuk shkarkohet" in prev
    client.post("/paneli/produktet/importi/%d/nis" % jid, data={"csrf_token": csrf(client, r.headers["Location"])})
    with app.app_context():
        con = _db()
        job = con.execute("SELECT * FROM import_jobs WHERE id=?", (jid,)).fetchone()
        assert job["status"] == "done" and job["created_n"] == 2 and job["updated_n"] == 1 and job["errors"] == 2
        assert con.execute("SELECT price, stock FROM products WHERE sku='FR-1050'").fetchone()[:] == (320, 31)
        assert con.execute("SELECT stock FROM products WHERE sku='PS-8020'").fetchone()[0] == 0  # empty → 0 (warning)
        assert con.execute("SELECT 1 FROM categories WHERE name_sq='Kategori e Re'").fetchone()
        assert not con.execute("SELECT 1 FROM product_images i JOIN products p ON p.id=i.product_id WHERE p.sku='UB-5044'").fetchone()
    err = client.get("/paneli/produktet/importi/%d/gabimet.csv" % jid)
    assert err.status_code == 200 and "Mungon SKU" in err.data.decode("utf-8-sig")


def test_csv_import_comma_and_tab_and_missing_columns(client, app):
    login(client)
    r = _import(client, b"sku,emri_sq,kategoria,cmimi\nX-1,Uje,Pije,60\n")
    assert r.status_code == 302
    r = _import(client, b"sku\temri_sq\tkategoria\tcmimi\nX-2\tLeng\tPije\t120\n")
    assert r.status_code == 302
    r = _import(client, b"emri;cmimi\nA;1\n")
    assert r.status_code == 400 and "Mungojnë kolonat" in r.text
    r = _import(client, b"sku;emri_sq;kategoria;cmimi\nX-3;Kafe;E panjohur;100\n", auto="0")
    prev = client.get(r.headers["Location"]).text
    assert "nuk ekziston" in prev


def test_csv_export_formula_injection_guard(client, app):
    with app.app_context():
        _db().execute("UPDATE products SET name_sq='=HYPERLINK(\"x\")' WHERE id=3002")
    login(client)
    data = client.get("/paneli/produktet?eksporto=csv").data.decode("utf-8-sig")
    assert "'=HYPERLINK" in data


def test_invoice_search_variants(client, app):
    with app.app_context():
        from enesai.services.demo_orders import seed_orders
        seed_orders(_db())
    login(client)
    for q, expect in (("EA-2026-00006", "EA-2026-00006"), ("6", None), ("muca", "EA-2026-00003"), ("+355684551290", "EA-2026-00005"),
                      ("m.daci@outlook.com", "EA-2026-00004"), ("VLORE10", "EA-2026-00006"), ("Hoxha Elira", "EA-2026-00006")):
        html = client.get("/paneli/faturat?q=" + q.replace("+", "%2B")).text
        if expect:
            first = re.search(r'class="ea-invlist__item"[^>]*>.*?<b class="ea-num">([^<]+)</b>', html, re.S)
            assert first and first.group(1) == expect, (q, first and first.group(1))


def test_order_status_flow_audited(client, app):
    with app.app_context():
        from enesai.services.demo_orders import seed_orders
        seed_orders(_db())
    login(client)
    tok = csrf(client, "/paneli/porosite")
    r = client.post("/paneli/porosite/EA-2026-00006/statusi", data={"csrf_token": tok, "status": "cancel"}, headers={"X-Requested-With": "fetch"})
    assert r.get_json()["ok"] and "kuponi u rikthye" in r.get_json()["message"]
    with app.app_context():
        assert _db().execute("SELECT status FROM coupons WHERE code='VLORE10'").fetchone()[0] == "active"
        assert _db().execute("SELECT COUNT(*) FROM audit_log WHERE action='Ndryshoi statusin'").fetchone()[0] >= 1


def test_audit_log_is_append_only(app):
    import sqlite3
    with app.app_context():
        con = _db()
        con.execute("INSERT INTO audit_log(at, action) VALUES ('2026-01-01T00:00:00','x')")
        for sql in ("UPDATE audit_log SET action='y'", "DELETE FROM audit_log"):
            try:
                con.execute(sql)
                assert False
            except sqlite3.DatabaseError as e:
                assert "append-only" in str(e)


def test_settings_validation_and_save(client, app):
    login(client)
    tok = csrf(client, "/paneli/cilesimet")
    r = client.post("/paneli/cilesimet", data={"csrf_token": tok, "nipt": "123", "whatsapp": "abc", "fee": "x", "store_lat": "200"})
    assert r.status_code == 200 and "NIPT" in r.text and "Asgjë nuk u ruajt" in r.text
    r = client.post("/paneli/cilesimet", data={"csrf_token": tok, "nipt": "l01234567a", "whatsapp": "+355 69 000 1111", "fee": "250", "freeOver": "4.000",
                                               "legalName": "Test shpk", "waMode": "api"})
    assert "Business API" in r.text  # API mode refused without credentials
    r = client.post("/paneli/cilesimet", data={"csrf_token": tok, "nipt": "l01234567a", "whatsapp": "+355 69 000 1111", "fee": "250", "freeOver": "4.000",
                                               "legalName": "Test shpk", "waMode": "manual", "address": "Rruga Test"})
    assert r.status_code == 302
    with app.app_context():
        from enesai.services import settings as st
        s = st.all_settings(_db())
        assert s["nipt"] == "L01234567A" and s["fee"] == "250" and s["freeOver"] == "4000"
    assert "Rruga Test" in client.get("/kontakt").text


def test_sample_invoice_and_reports_csv(client):
    login(client)
    assert client.get("/paneli/cilesimet/fature-shembull.pdf").data[:4] == b"%PDF"
    r = client.get("/paneli/raportet?eksporto=csv")
    assert r.status_code == 200 and r.data.decode("utf-8-sig").startswith("Data;Porosi")


def test_admin_pages_render(client):
    login(client)
    for p in ("/paneli/", "/paneli/operatoret", "/paneli/produktet", "/paneli/produktet/1050", "/paneli/kategorite", "/paneli/produktet/importi",
              "/paneli/porosite", "/paneli/faturat", "/paneli/kuponat", "/paneli/abonentet", "/paneli/email", "/paneli/reklamat", "/paneli/raportet",
              "/paneli/regjistri", "/paneli/cilesimet"):
        assert client.get(p).status_code == 200, p


def test_reset_password_clears_lockout_and_sessions(client, app):
    from conftest import OWNER_PW
    for _ in range(6):
        login(client, password="gabim-gabim-1")
    assert login(client).status_code == 429  # locked even with the right password
    with app.app_context():
        from enesai.db import get_db
        from enesai.services.auth import reset_password
        assert reset_password("nuk-ekziston", "Fjalekalim-i-Ri-2026") == "Nuk ekziston përdorues me këtë emër."
        assert reset_password("pronari", "Shkurt-1")  # too short → error text
        assert reset_password("PRONARI", "Fjalekalim-i-Ri-2026") is None
        assert get_db().execute("SELECT COUNT(*) FROM login_attempts WHERE username='pronari'").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE 'Rivendosi%'").fetchone()[0] == 1
    assert login(client, password=OWNER_PW).status_code == 401
    assert login(client, password="Fjalekalim-i-Ri-2026").status_code == 302


def test_login_page_explains_missing_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("ENESAI_INSTANCE", str(tmp_path / "bosh"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-not-for-production")
    from enesai import create_app
    c = create_app(TESTING=True).test_client()
    r = login(c, username="admin", password="cfaredo-1234")
    assert r.status_code == 401
    assert "Pronari nuk është krijuar ende" in r.text and "nis.bat" in r.text
