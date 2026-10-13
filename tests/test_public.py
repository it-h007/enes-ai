from urllib.parse import unquote

import pytest

from conftest import add_to_cart, csrf

PAGES = ["/", "/dyqani", "/oferta", "/kategorite", "/kategoria/fruta-perime", "/produkt/1050", "/shporta", "/rreth-nesh", "/kontakt",
         "/kushtet", "/njoftime", "/robots.txt", "/sitemap.xml", "/dyqani?q=avokado", "/dyqani?rendit=cmimi-asc&oferta=1"]


@pytest.mark.parametrize("path", PAGES)
def test_public_pages_ok(client, path):
    r = client.get(path)
    assert r.status_code == 200


def test_neox_credit_is_last_visible_element(client):
    html = client.get("/").text
    footer, credit = html.index('class="ea-footer"'), html.index('class="ea-credit"')
    assert footer < credit and "NEOX Web Studio" in html[credit:credit + 600]


def test_home_has_no_add_to_cart_and_20_categories(client):
    html = client.get("/").text
    assert 'data-ea="add"' not in html.split('<main id="main">')[1].split("</main>")[0]
    assert html.count('class="ea-catcard"') == 20
    for name in ("Kancelari", "Lodra", "Produkte Festive", "Enë Kuzhine", "Veshmbathje", "Tekstil"):
        assert name in html
    assert "ea-catcard--fill7" in html  # 7th slot of the last desktop row
    assert 'href="/oferta"' in html  # CR-08 working offers link


def test_404_status_and_page(client):
    r = client.get("/nuk-ekziston")
    assert r.status_code == 404 and "Kjo faqe nuk u gjet" in r.text
    assert client.get("/produkt/999999").status_code == 404
    assert client.get("/kategoria/nuk-ka").status_code == 404


def test_hidden_product_not_public(client, app):
    with app.app_context():
        from enesai.db import get_db
        get_db().execute("UPDATE products SET visible=0 WHERE id=1050")
    assert client.get("/produkt/1050").status_code == 404
    assert "Avokado" not in client.get("/dyqani").text


def test_search_accent_insensitive_and_api(client):
    assert "Qumësht i freskët" in client.get("/dyqani?q=qumesht").text
    j = client.get("/api/kerko?q=djathe").get_json()
    assert j["total"] == 1 and j["products"][0]["name"] == "Djathë i bardhë"
    assert client.get("/api/kerko?q=zzzz").get_json()["total"] == 0


def test_search_fallback_without_fts(client, app):
    with app.app_context():
        from enesai.db import get_db
        get_db().execute("DROP TABLE products_fts")
    assert "Qumësht" in client.get("/dyqani?q=qumesht").text


def test_pagination_large_catalog(client, app):
    with app.app_context():
        import seed
        from enesai.db import get_db
        seed.bulk(get_db(), 120)
    html = client.get("/dyqani?stok=0").text
    assert "Faqja 1 nga" in html and 'href="/dyqani?stok=0&amp;faqe=2"' in html
    page2 = client.get("/dyqani?stok=0&faqe=2").text
    assert 'aria-current="page">2<' in page2
    assert client.get("/dyqani?faqe=9999").status_code == 200  # clamps


def test_filters_price_and_sale(client):
    html = client.get("/dyqani?oferta=1").text
    assert "Avokado" in html and "Qumësht" not in html
    html = client.get("/dyqani?cmimi_min=900").text
    assert "Vaj ulliri" in html and "Banane" not in html


def test_discount_rounding_half_up():
    from enesai.util import discounted, lek, round_half_up
    assert discounted(140, 15) == 119 and discounted(300, 20) == 240 and discounted(500, 10) == 450
    assert round_half_up(2567 * 15, 100) == 385  # 385.05
    assert discounted(5, 50) == 3  # 2.5 → 3 (half up)
    assert lek(2370) == "2.370 L" and lek(1234567) == "1.234.567 L"


def test_totals_threshold_after_coupon():
    from enesai.services.totals import totals
    t = totals([(3527, 1)], 15, 200, 3000)  # sample PDF EA-2026-00149: 3.527 − 529 = 2.998 < 3.000
    assert t["discount"] == 529 and t["fee"] == 200 and t["total"] == 3198
    t2 = totals([(3600, 1)], 10, 200, 3000)
    assert t2["fee"] == 0
    assert totals([], 0, 200, 3000)["fee"] == 0
    assert totals([(100, 1)], 0, 200, 0)["fee"] == 200  # 0 = no free delivery


def test_cart_quantity_cap_and_stock(client):
    j = add_to_cart(client, 2107, 50)  # Mish pule: stock 4
    assert j["qty"] == 4 and j["capped"]
    j = add_to_cart(client, 1042, 30)  # stock 120, cap 20
    assert j["qty"] == 20


def test_cart_requires_csrf(client):
    r = client.post("/shporta/shto", data={"product": 1050}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400


def test_adult_category_not_orderable(client, app):
    with app.app_context():
        from enesai.db import get_db
        con = get_db()
        cid = con.execute("SELECT id FROM categories WHERE slug='pije-alkoolike'").fetchone()[0]
        con.execute("UPDATE products SET category_id=? WHERE id=3002", (cid,))
    tok = csrf(client)
    r = client.post("/shporta/shto", data={"csrf_token": tok, "product": 3002}, headers={"X-Requested-With": "fetch"})
    assert r.status_code == 400 and r.get_json()["error"] == "adult"


def test_newsletter_states(client):
    tok = csrf(client)
    h = {"X-Requested-With": "fetch"}
    assert client.post("/abonohu", data={"csrf_token": tok, "email": "jo-email"}, headers=h).get_json()["error"] == "invalid"
    assert client.post("/abonohu", data={"csrf_token": tok, "email": "klient@shembull.al"}, headers=h).get_json()["ok"]
    assert client.post("/abonohu", data={"csrf_token": tok, "email": "Klient@Shembull.al"}, headers=h).get_json()["error"] == "duplicate"


def test_unsubscribe(client, app):
    tok = csrf(client)
    client.post("/abonohu", data={"csrf_token": tok, "email": "c@shembull.al"}, headers={"X-Requested-With": "fetch"})
    with app.app_context():
        from enesai.db import get_db
        t = get_db().execute("SELECT token FROM subscribers WHERE email='c@shembull.al'").fetchone()[0]
    assert client.get("/cabonohu/" + t).status_code == 200
    client.post("/cabonohu/" + t, data={"csrf_token": csrf(client, "/cabonohu/" + t)})
    with app.app_context():
        from enesai.db import get_db
        assert get_db().execute("SELECT active FROM subscribers WHERE email='c@shembull.al'").fetchone()[0] == 0
    assert client.get("/cabonohu/xxxxxxxx").status_code == 404


def test_security_headers(client):
    r = client.get("/")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["X-Content-Type-Options"] == "nosniff"
    c = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in c and "SameSite=Lax" in c


def test_language_switch(client):
    r = client.get("/?lang=en")
    assert "ea_lang=en" in r.headers.get("Set-Cookie", "")
    assert '<html lang="en"' in r.text and "Shop Online" in r.text


def test_whatsapp_url_encoding():
    from enesai.util import maps_url, wa_url
    text = "Vendndodhja: " + maps_url(40.45391, 19.48307) + "\nTOTALI: 1.000 L"
    u = wa_url("355691234567", text)
    assert u.startswith("https://wa.me/355691234567?text=")
    assert "&" not in u.split("?", 1)[1]  # the Maps '&query=' is encoded as %26
    assert unquote(u.split("text=", 1)[1]) == text


def test_e164_normalisation_keeps_country_code():
    from enesai.util import e164_digits
    assert e164_digits("069 123 4567") == "355691234567"  # prototype defect X8 fixed
    assert e164_digits("+355 69 123 4567") == "355691234567"
    assert e164_digits("00355691234567") == "355691234567"
    assert e164_digits("+44 775 156 4698") == "447751564698"


def test_main_categories_are_real_not_demo(app):
    with app.app_context():
        import seed
        from enesai.db import get_db
        con = get_db()
        seed.purge(con)
        assert con.execute("SELECT COUNT(*) FROM categories WHERE parent_id IS NULL").fetchone()[0] == 20
        assert con.execute("SELECT COUNT(*) FROM categories WHERE is_demo = 1").fetchone()[0] == 0
