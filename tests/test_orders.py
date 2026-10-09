import re
import secrets
import threading

from conftest import CHECKOUT, add_to_cart, checkout, csrf


def _db(app):
    from enesai.db import get_db
    return get_db()


def test_checkout_full_flow_and_snapshots(client, app):
    add_to_cart(client, 1050, 2)
    r, idem, _ = checkout(client)
    assert r.status_code == 302
    loc = r.headers["Location"]
    m = re.match(r"/porosia/(EA-\d{4}-\d{5})\?t=(.+)$", loc)
    assert m, loc
    nr, token = m.groups()
    page = client.get(loc)
    assert page.status_code == 200 and nr in page.text and "Dërgo faturën në WhatsApp" in page.text
    with app.app_context():
        con = _db(app)
        o = con.execute("SELECT * FROM orders WHERE nr=?", (nr,)).fetchone()
        assert o["subtotal"] == 480 and o["delivery"] == 200 and o["total"] == 680
        assert o["lat"] == 40.45391 and o["loc_source"] == "map"
        it = con.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)).fetchone()
        assert it["unit_price"] == 240 and it["name"] == "Avokado Hass"
        assert con.execute("SELECT stock FROM products WHERE id=1050").fetchone()[0] == 28
        # price change later does not alter the stored order
        con.execute("UPDATE products SET price=999, sale_price=999 WHERE id=1050")
    assert "480" in client.get(loc).text


def test_server_validation_errors(client):
    add_to_cart(client)
    r, _, _ = checkout(client, name="", phone="12345", lat="", lng="", terms="")
    assert r.status_code == 422
    for lbl in ("Emri", "Telefoni", "Vendndodhja", "Kushtet"):
        assert lbl in r.text


def test_gps_validation(client):
    add_to_cart(client)
    for bad in ({"lat": "95", "lng": "19"}, {"lat": "abc"}, {"loc_source": "typed"}, {"lat": "0", "lng": "0"}):
        r, _, _ = checkout(client, **bad)
        assert r.status_code == 422, bad


def test_email_optin_and_landline_rejected(client, app):
    add_to_cart(client)
    r, _, _ = checkout(client, phone="033 123 456")
    assert r.status_code == 422
    r, _, _ = checkout(client, email="klient@shembull.al", optin="1")
    assert r.status_code == 302
    with app.app_context():
        assert _db(app).execute("SELECT source FROM subscribers WHERE email='klient@shembull.al'").fetchone()[0] == "arka"


def test_idempotent_double_submit(client, app):
    add_to_cart(client)
    r, idem, tok = checkout(client)
    assert r.status_code == 302
    add_to_cart(client)  # cart refilled, same idempotency key re-posted
    data = dict(CHECKOUT, csrf_token=tok, idem=idem, action="order")
    r2 = client.post("/arka", data=data)
    assert r2.status_code == 302 and r2.headers["Location"].split("?")[0] == r.headers["Location"].split("?")[0]
    with app.app_context():
        assert _db(app).execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_empty_cart_redirects(client):
    assert client.get("/arka").headers["Location"].endswith("/shporta")


def test_insufficient_stock_rejected(client, app):
    add_to_cart(client, 2107, 4)
    with app.app_context():
        _db(app).execute("UPDATE products SET stock=1 WHERE id=2107")
    r, _, _ = checkout(client)
    # cart clamps to the new stock before checkout; order is created for 1 unit only
    with app.app_context():
        o = _db(app).execute("SELECT items_count FROM orders").fetchone()
    assert r.status_code == 302 and o[0] == 1


def test_coupon_applied_recomputed_and_single_use(client, app):
    add_to_cart(client, 1050, 2)
    tok = csrf(client, "/arka")
    j = client.post("/api/kupon/kontrollo", data={"csrf_token": tok, "code": "klient15"}, headers={"X-Requested-With": "fetch"}).get_json()
    assert j["ok"] and j["pct"] == 15 and "−72" in j["final"]
    r, _, _ = checkout(client, coupon="KLIENT15")
    assert r.status_code == 302
    nr = r.headers["Location"].split("/")[2].split("?")[0]
    with app.app_context():
        con = _db(app)
        o = con.execute("SELECT * FROM orders WHERE nr=?", (nr,)).fetchone()
        assert o["coupon_code"] == "KLIENT15" and o["discount"] == 72 and o["total"] == 480 - 72 + 200
        c = con.execute("SELECT * FROM coupons WHERE code='KLIENT15'").fetchone()
        assert c["status"] == "used" and c["used_order_nr"] == nr
    # second use refused
    c2 = app.test_client()
    add_to_cart(c2)
    tok = csrf(c2, "/arka")
    j = c2.post("/api/kupon/kontrollo", data={"csrf_token": tok, "code": "KLIENT15"}, headers={"X-Requested-With": "fetch"}).get_json()
    assert not j["ok"] and j["error"] == "used"
    r, _, _ = checkout(c2, coupon="KLIENT15")
    assert r.status_code == 409 and "Kuponi nuk vlen më" in r.text


def test_expired_and_unknown_coupon(client):
    add_to_cart(client)
    tok = csrf(client, "/arka")
    h = {"X-Requested-With": "fetch"}
    assert client.post("/api/kupon/kontrollo", data={"csrf_token": tok, "code": "VERA20"}, headers=h).get_json()["error"] == "expired"
    assert client.post("/api/kupon/kontrollo", data={"csrf_token": tok, "code": "NUKKA"}, headers=h).get_json()["error"] == "missing"
    assert client.post("/api/kupon/kontrollo", data={"csrf_token": tok, "code": ""}, headers=h).get_json()["error"] == "empty"


def _order(app, coupon=None, items=((1042, 1),)):
    from enesai.services import orders
    v = dict(name="A", surname="B", phone="0691234567", email="", optin=False, city="Vlorë", zone="", address="Rruga 1, Pall 2", note="", terms=True, pay="cash")
    return orders.create_order(v, {"lat": 40.45, "lng": 19.48, "src": "map", "acc": None}, list(items), coupon, secrets.token_urlsafe(24))


def test_coupon_race_only_one_wins(app):
    results = []

    def worker():
        with app.app_context():
            try:
                _order(app, "VLORE10")
                results.append("ok")
            except Exception as e:  # CouponError
                results.append(type(e).__name__)
            finally:
                from enesai.db import close_db
                close_db()
    ths = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert results.count("ok") == 1 and results.count("CouponError") == 7
    with app.app_context():
        assert _db(app).execute("SELECT COUNT(*) FROM orders WHERE coupon_code='VLORE10'").fetchone()[0] == 1


def test_order_numbers_unique_under_concurrency(app):
    nrs = []

    def worker():
        with app.app_context():
            try:
                o, _ = _order(app)
                nrs.append(o["nr"])
            finally:
                from enesai.db import close_db
                close_db()
    ths = [threading.Thread(target=worker) for _ in range(12)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert len(nrs) == 12 and len(set(nrs)) == 12
    assert all(re.match(r"^EA-\d{4}-\d{5}$", n) for n in nrs)


def test_cancel_returns_coupon_and_stock_and_is_final(app):
    with app.app_context():
        from enesai.services import orders
        con = _db(app)
        before = con.execute("SELECT stock FROM products WHERE id=1042").fetchone()[0]
        o, _ = _order(app, "VLORE10", ((1042, 3),))
        assert con.execute("SELECT stock FROM products WHERE id=1042").fetchone()[0] == before - 3
        _o2, returned = orders.change_status(o["nr"], "cancel", None)
        assert returned
        assert con.execute("SELECT status FROM coupons WHERE code='VLORE10'").fetchone()[0] == "active"
        assert con.execute("SELECT stock FROM products WHERE id=1042").fetchone()[0] == before
        try:
            orders.change_status(o["nr"], "prep", None)
            assert False, "cancel must be final"
        except orders.OrderError as e:
            assert e.code == "cancelled_final"


def test_confirmation_and_pdf_need_token(client, app):
    add_to_cart(client)
    r, _, _ = checkout(client)
    loc = r.headers["Location"]
    nr, token = re.match(r"/porosia/(.+)\?t=(.+)", loc).groups()
    other = app.test_client()
    assert other.get("/porosia/" + nr).status_code == 404
    assert other.get("/porosia/%s?t=%s" % (nr, "x" * 32)).status_code == 404
    assert other.get("/porosia/%s/fatura.pdf" % nr).status_code == 404
    assert other.get("/porosia/%s/fatura.pdf?t=%s" % (nr, token)).status_code == 200  # link works without the session (sharable by the customer)
    assert other.get("/paneli/faturat/%s.pdf" % nr).status_code == 302  # admin route requires login


def test_pdf_has_clickable_maps_link_qr_and_unicode(client, app):
    add_to_cart(client, 3011, 1)
    r, _, _ = checkout(client, name="Ëndrit", surname="Çela", note="Zileja e dytë – “porta”")
    pdf = client.get(r.headers["Location"].replace("?t=", "/fatura.pdf?t=")).data
    assert pdf[:4] == b"%PDF"
    assert b"/URI (https://www.google.com/maps/search/?api=1&query=40.453910,19.483070)" in pdf
    from pypdf import PdfReader
    import io
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    for s in ("FATURË POROSIE", "Ëndrit Çela", "Djathë i bardhë", "Faqja 1/1", "Hap në Google Maps"):
        assert s in text, s


def test_whatsapp_text_and_wa_mark(client, app):
    with app.app_context():
        from enesai.services import settings as st
        st.save({"whatsapp": "069 000 1111"})
    add_to_cart(client, 1050, 1)
    r, _, _ = checkout(client)
    page = client.get(r.headers["Location"]).text
    href = re.search(r'href="(https://wa\.me/[^"]+)"', page).group(1)
    assert href.startswith("https://wa.me/355690001111?text=POROSI%20E%20RE")
    nr, token = re.match(r"/porosia/(.+)\?t=(.+)", r.headers["Location"]).groups()
    tok = csrf(client, r.headers["Location"])
    assert client.post("/porosia/%s/wa" % nr, data={"csrf_token": tok, "t": token}).status_code == 204
    with app.app_context():
        o = _db(app).execute("SELECT wa_opened_at, wa_sent_at FROM orders WHERE nr=?", (nr,)).fetchone()
        assert o["wa_opened_at"] and o["wa_sent_at"] is None  # opened ≠ verified sent


def test_seller_snapshot_is_immutable(client, app):
    with app.app_context():
        from enesai.services import settings as st
        st.save({"legalName": "Subjekti i Vjetër shpk"})
    add_to_cart(client)
    r, _, _ = checkout(client)
    with app.app_context():
        from enesai.services import settings as st
        st.save({"legalName": "Emër i Ri"})
    assert "Subjekti i Vjetër shpk" in client.get(r.headers["Location"]).text
