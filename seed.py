"""Demo content for development and visual checks — NOT store data.

The 20 main categories are real store data (migration 0002) and are never demo;
sub-categories, products, announcements, coupons and orders created here are demo.

Every row inserted here has is_demo = 1 and is shown with a “DEMO” marker in the admin.
Names, prices, stock, phones and people are fictitious (same demo set as the approved
prototype so the screens can be compared with the screenshots).

    python seed.py              → insert the demo catalogue, announcements, coupons and orders
    python seed.py --purge-demo → delete every demo row (keeps real data)
    python seed.py --bulk 20000 → add N synthetic demo products (performance testing)
"""
import random
import sys

from enesai import create_app
from enesai.db import get_db, transaction
from enesai.services.catalog import build_search_text
from enesai.util import discounted, now_iso

S = "/static/img/categories/"
CATS = [
    ("fruta-perime", "Fruta & Perime", "Fruit & Vegetables", ["Fruta", "Perime", "Zarzavate", "Fruta të thata"]),
    ("mish-peshk", "Mish & Peshk", "Meat & Fish", ["Mish pule", "Mish viçi", "Peshk i freskët", "Fruta deti"]),
    ("bulmet", "Bulmet", "Dairy", ["Qumësht", "Djathë", "Kos", "Gjalpë & Ajkë"]),
    ("buke-pasticeri", "Bukë & Pastiçeri", "Bakery", ["Bukë", "Pastiçeri", "Kruasan", "Biskota"]),
    ("ushqime-baze", "Ushqime Bazë", "Pantry", ["Makarona", "Oriz & Drithëra", "Vaj & Uthull", "Konserva"]),
    ("pije", "Pije", "Drinks", ["Ujë", "Lëngje", "Pije të gazuara", "Pije energjike"]),
    ("snack-embelsira", "Snack & Ëmbëlsira", "Snacks & Sweets", ["Çokollata", "Patatina", "Fara & Arra", "Ëmbëlsira"]),
    ("produkte-shtepie", "Produkte Shtëpie", "Household", ["Pastrim", "Lavanderi", "Letër & Higjienë", "Kuzhina"]),
    ("pije-alkoolike", "Pije Alkoolike", "Alcoholic Drinks", ["Verë", "Birrë", "Raki", "Pije të forta"]),
    ("produkte-te-ngrira", "Produkte të Ngrira", "Frozen Food", ["Perime të ngrira", "Mish & peshk i ngrirë", "Akullore", "Gatime të gata"]),
    ("kafe-caj", "Kafe & Çaj", "Coffee & Tea", ["Kafe", "Espresso & kapsula", "Çaj", "Kakao"]),
    ("kujdes-personal", "Kujdes Personal", "Personal Care", ["Higjienë orale", "Kujdes për flokët", "Kujdes për trupin", "Deodorantë"]),
    ("produkte-per-bebe", "Produkte për Bebe", "Baby Products", ["Pelena", "Ushqim për bebe", "Higjiena e bebes", "Aksesorë"]),
    ("produkte-per-kafshe", "Produkte për Kafshë", "Pet Supplies", ["Ushqim për qen", "Ushqim për mace", "Rërë & higjienë", "Aksesorë"]),
]
P = "/static/img/products/"
DESC_AVOKADO = ("Avokado Hass e pjekur në pikën e duhur — me tul të butë dhe shije arre. E përshtatshme për sallata, "
                "tost me avokado ose guacamole. Ruajeni në temperaturë ambienti derisa të zbutet, pastaj në frigorifer.")
# (id, sku, name, en, pack, price, pct, cat, sub, images, stock, brand, desc)
PRODUCTS = [
    (1042, "FR-1042", "Banane", "Bananas", "1 kg", 200, 20, "fruta-perime", "Fruta", ["prod-banane.jpg"], 120, "Import · Ekuador", ""),
    (1043, "FR-1043", "Domate", "Tomatoes", "1 kg", 140, 15, "fruta-perime", "Perime", ["prod-domate.jpg"], 64, "Prodhim vendi", ""),
    (2107, "MP-2107", "Mish pule", "Chicken breast", "1 kg", 500, 10, "mish-peshk", "Mish pule", ["prod-mish-pule.jpg"], 4, "Fermë vendase", ""),
    (3011, "BU-3011", "Djathë i bardhë", "White cheese", "500 g", 450, 0, "bulmet", "Djathë", ["prod-djathe-bardhe.jpg"], 38, "Bulmetore vendase", ""),
    (3002, "BU-3002", "Qumësht i freskët", "Fresh milk", "1 L", 150, 0, "bulmet", "Qumësht", ["prod-qumesht.jpg"], 90, "", ""),
    (4005, "BK-4005", "Bukë e fërgër", "Fresh bread", "400 g", 80, 0, "buke-pasticeri", "Bukë", ["prod-buke.jpg"], 40, "Furra e ditës", ""),
    (5020, "UB-5020", "Vezë fshati", "Free-range eggs", "6 copë", 180, 0, "ushqime-baze", "Konserva", ["prod-veze.jpg"], 55, "Fermë vendase", ""),
    (5031, "UB-5031", "Vaj ulliri ekstra i virgjër", "Extra virgin olive oil", "1 L", 980, 0, "ushqime-baze", "Vaj & Uthull", ["prod-vaj-ulliri.jpg"], 22, "Ullishte Vlorë", ""),
    (1050, "FR-1050", "Avokado Hass", "Hass avocado", "2 copë", 300, 20, "fruta-perime", "Fruta", ["prod-avokado.jpg", "prod-avokado-2.jpg", "prod-avokado-3.jpg"], 30, "Import · Spanjë", DESC_AVOKADO),
]
ANN = [
    ("reklame", "Vaj ulliri nga Vlora", "Prodhim vendi, i shtypur në të ftohtë. Gjeni në raftin e ushqimeve bazë.", P + "prod-vaj-ulliri.jpg", 1, "/produkt/5031", "Shiko produktin", 1, "2026-09-29T08:00:00", ""),
    ("njoftim", "Orari i festave", "Orari i hapjes për ditët e festave do të publikohet këtu nga stafi.", "/static/img/photography/storefront-night.jpg", 0, "", "Lexo njoftimin", 2, "2026-10-06T08:00:00", ""),
    ("pune", "Kërkojmë arkëtar/e", "Bashkohuni me ekipin tonë në Vlorë. Aplikoni në dyqan ose me email.", "/static/img/photography/dark-produce.jpg", 0, "", "Detajet e punës", 3, "2026-10-02T08:00:00", ""),
    ("reklame", "Bukë e fërgër çdo mëngjes", "Furra e ditës — bukë e freskët nga ora e hapjes.", P + "prod-buke.jpg", 1, "/produkt/4005", "Shiko bukën", 4, "2026-09-24T08:00:00", ""),
    ("njoftim", "Dërgesa në shtëpi në Vlorë", "Porositni online dhe paguani me cash në dorëzim.", "/static/img/photography/promo-van.jpg", 0, "", "", 5, "2026-09-18T08:00:00", ""),
    ("pune", "Punonjës/e për sektorin e frutave", "Rregullim i rafteve dhe kujdes për freskinë e produkteve.", "/static/img/photography/hero-market.jpg", 0, "", "", 6, "2026-09-12T08:00:00", ""),
]
JOB_BODY = ("ENES’AI Super Market në Vlorë kërkon një arkëtar/e me kohë të plotë. Kërkojmë dikë të sjellshëm, të saktë me paratë "
            "dhe që i pëlqen të punojë me njerëz.\n\n## Çfarë ofrojmë\nAmbient pune të rregullt, trajnim në fillim dhe ekip që "
            "ndihmon njëri-tjetrin.\n\n## Si të aplikoni\nEjani në dyqan me CV ose na shkruani në email. Kontaktet janë në faqen Kontakt.")
COUPONS = [
    ("VLORE10", 10, "Pronari", "2026-10-05T09:12:00", None, "Për provë — demo"),
    ("KLIENT15", 15, "Pronari", "2026-10-06T10:40:00", "2026-12-31", "Klient i rregullt — demo"),
    ("VERA20", 20, "Pronari", "2026-07-01T09:00:00", "2026-09-30", "Oferta e verës — demo"),
]


def seed(con):
    if con.execute("SELECT COUNT(*) FROM products WHERE is_demo = 1").fetchone()[0]:
        print("Të dhënat demo ekzistojnë tashmë.")
        return
    t = now_iso()
    from enesai.util import slugify
    with transaction(con):
        ids = {}
        for i, (slug, name, en, subs) in enumerate(CATS):
            # main categories are real store data (migration 0002); only reuse them here
            row = con.execute("SELECT id FROM categories WHERE slug = ? AND parent_id IS NULL", (slug,)).fetchone()
            if row:
                ids[slug] = row[0]
            else:
                ids[slug] = con.execute("INSERT INTO categories(slug, name_sq, name_en, image, sort, visible, adult, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,1,?,0,?,?)",
                                        (slug, name, en, S + "cat-" + slug + ".jpg", i + 1, 1 if slug == "pije-alkoolike" else 0, t, t)).lastrowid
            for j, sub in enumerate(subs):
                sslug = slug + "-" + slugify(sub)
                row = con.execute("SELECT id FROM categories WHERE slug = ?", (sslug,)).fetchone()
                ids[(slug, sub)] = row[0] if row else con.execute(
                    "INSERT INTO categories(slug, name_sq, name_en, parent_id, image, sort, visible, is_demo, created_at, updated_at) VALUES (?,?,?,?,?,?,1,1,?,?)",
                    (sslug, sub, "", ids[slug], "", j + 1, t, t)).lastrowid
        for (pid, sku, name, en, pack, price, pct, cat, sub, imgs, stock, brand, desc) in PRODUCTS:
            cname = [c[1] for c in CATS if c[0] == cat][0]
            con.execute("""INSERT INTO products(id, sku, name_sq, name_en, desc_sq, brand, packaging, unit, price, discount_pct, sale_price, stock,
                           low_threshold, visible, category_id, subcategory_id, search_text, is_demo, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,5,1,?,?,?,1,?,?)""",
                        (pid, sku, name, en, desc, brand, pack, "copë", price, pct, discounted(price, pct), stock, ids[cat], ids[(cat, sub)],
                         build_search_text(name, en, brand, sku, pack, [cname, sub]), t, t))
            for k, img in enumerate(imgs):
                con.execute("INSERT INTO product_images(product_id, path, sort) VALUES (?,?,?)", (pid, P + img, k))
        for (typ, title, summary, img, contain, link, label, sort, start, end) in ANN:
            con.execute("""INSERT INTO announcements(type, title_sq, summary_sq, body_sq, image, image_contain, link, link_label, starts_at, ends_at,
                           published, on_home, sort, job_position, job_schedule, job_place, job_deadline, is_demo, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,1,?,?)""",
                        (typ, title, summary, JOB_BODY if title.startswith("Kërkojmë") else summary, img, contain, link, label, start, end or None,
                         1 if sort <= 4 else 0, sort, "Arkëtar/e" if typ == "pune" and sort == 3 else "", "Kohë e plotë" if typ == "pune" else "",
                         "Vlorë" if typ == "pune" else "", "", t, t))
        for code, pct, by, created, until, note in COUPONS:
            con.execute("INSERT INTO coupons(code, pct, status, created_by_name, created_at, ends_on, note, is_demo) VALUES (?,?, 'active', ?,?,?,?,1)",
                        (code, pct, by, created, until, note))
            con.execute("INSERT INTO coupon_events(code, event, at, by_name) VALUES (?, 'created', ?, ?)", (code, created, by))
    print("U shtuan të dhënat demo: nënkategori për %d kategori, %d produkte, %d njoftime, %d kupona." % (len(CATS), len(PRODUCTS), len(ANN), len(COUPONS)))


def bulk(con, n):
    cats = con.execute("SELECT id, name_sq FROM categories WHERE parent_id IS NULL").fetchall()
    words = ["Krem", "Lëng", "Ujë", "Biskota", "Makarona", "Oriz", "Sapun", "Detergjent", "Kafe", "Çaj", "Djathë", "Kos", "Salcë", "Fasule"]
    base = con.execute("SELECT COALESCE(MAX(id), 100000) FROM products").fetchone()[0] + 1
    t = now_iso()
    rnd = random.Random(7)
    with transaction(con):
        for i in range(n):
            c = rnd.choice(cats)
            name = "%s %s %d" % (rnd.choice(words), rnd.choice(["Premium", "Klasik", "Bio", "Fresh", "Mini"]), i)
            price = rnd.randrange(50, 3000)
            pct = rnd.choice([0, 0, 0, 10, 20])
            sku = "DEMO-%06d" % (base + i)
            con.execute("""INSERT INTO products(id, sku, name_sq, price, discount_pct, sale_price, stock, visible, category_id, search_text, is_demo, created_at, updated_at, packaging)
                           VALUES (?,?,?,?,?,?,?,1,?,?,1,?,?, '1 copë')""",
                        (base + i, sku, name, price, pct, discounted(price, pct), rnd.randrange(0, 80), c["id"],
                         build_search_text(name, "", "", sku, "", [c["name_sq"]]), t, t))
    print("U shtuan %d produkte demo sintetike." % n)


def purge(con):
    with transaction(con):
        con.execute("DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE is_demo = 1)")
        con.execute("DELETE FROM orders WHERE is_demo = 1")
        con.execute("DELETE FROM coupons WHERE is_demo = 1")
        con.execute("DELETE FROM subscribers WHERE is_demo = 1")
        con.execute("DELETE FROM announcements WHERE is_demo = 1")
        con.execute("DELETE FROM products WHERE is_demo = 1")
        con.execute("DELETE FROM categories WHERE is_demo = 1 AND parent_id IS NOT NULL")
        con.execute("DELETE FROM categories WHERE is_demo = 1")
    print("Të dhënat demo u fshinë.")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        con = get_db()
        if "--purge-demo" in sys.argv:
            purge(con)
        elif "--bulk" in sys.argv:
            bulk(con, int(sys.argv[sys.argv.index("--bulk") + 1]))
        else:
            seed(con)
            if "--no-orders" not in sys.argv:
                try:
                    from enesai.services.demo_orders import seed_orders
                    seed_orders(con)
                except ImportError:
                    pass
