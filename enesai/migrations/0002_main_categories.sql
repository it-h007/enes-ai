-- The 20 main categories of the store are real data (CR-07 + client request Oct 2026:
-- Kancelari, Lodra, Produkte Festive, Enë Kuzhine, Veshmbathje, Tekstil).
-- Existing rows with the same slug (e.g. created by seed.py) are kept and marked real.
INSERT OR IGNORE INTO categories(slug, name_sq, name_en, image, sort, visible, adult, is_demo, created_at, updated_at) VALUES
 ('fruta-perime', 'Fruta & Perime', 'Fruit & Vegetables', '/static/img/categories/cat-fruta-perime.jpg', 1, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('mish-peshk', 'Mish & Peshk', 'Meat & Fish', '/static/img/categories/cat-mish-peshk.jpg', 2, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('bulmet', 'Bulmet', 'Dairy', '/static/img/categories/cat-bulmet.jpg', 3, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('buke-pasticeri', 'Bukë & Pastiçeri', 'Bakery', '/static/img/categories/cat-buke-pasticeri.jpg', 4, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('ushqime-baze', 'Ushqime Bazë', 'Pantry', '/static/img/categories/cat-ushqime-baze.jpg', 5, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('pije', 'Pije', 'Drinks', '/static/img/categories/cat-pije.jpg', 6, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('snack-embelsira', 'Snack & Ëmbëlsira', 'Snacks & Sweets', '/static/img/categories/cat-snack-embelsira.jpg', 7, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('produkte-shtepie', 'Produkte Shtëpie', 'Household', '/static/img/categories/cat-produkte-shtepie.jpg', 8, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('pije-alkoolike', 'Pije Alkoolike', 'Alcoholic Drinks', '/static/img/categories/cat-pije-alkoolike.jpg', 9, 1, 1, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('produkte-te-ngrira', 'Produkte të Ngrira', 'Frozen Food', '/static/img/categories/cat-produkte-te-ngrira.jpg', 10, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('kafe-caj', 'Kafe & Çaj', 'Coffee & Tea', '/static/img/categories/cat-kafe-caj.jpg', 11, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('kujdes-personal', 'Kujdes Personal', 'Personal Care', '/static/img/categories/cat-kujdes-personal.jpg', 12, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('produkte-per-bebe', 'Produkte për Bebe', 'Baby Products', '/static/img/categories/cat-produkte-per-bebe.jpg', 13, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('produkte-per-kafshe', 'Produkte për Kafshë', 'Pet Supplies', '/static/img/categories/cat-produkte-per-kafshe.jpg', 14, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('kancelari', 'Kancelari', 'Stationery', '/static/img/categories/cat-kancelari.jpg', 15, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('lodra', 'Lodra', 'Toys', '/static/img/categories/cat-lodra.jpg', 16, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('produkte-festive', 'Produkte Festive', 'Festive Products', '/static/img/categories/cat-produkte-festive.jpg', 17, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('ene-kuzhine', 'Enë Kuzhine', 'Kitchenware', '/static/img/categories/cat-ene-kuzhine.jpg', 18, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('veshmbathje', 'Veshmbathje', 'Clothing & Footwear', '/static/img/categories/cat-veshmbathje.jpg', 19, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
 ('tekstil', 'Tekstil', 'Home Textiles', '/static/img/categories/cat-tekstil.jpg', 20, 1, 0, 0, strftime('%Y-%m-%dT%H:%M:%S','now','localtime'), strftime('%Y-%m-%dT%H:%M:%S','now','localtime'));
UPDATE categories SET is_demo = 0 WHERE parent_id IS NULL AND slug IN ('fruta-perime','mish-peshk','bulmet','buke-pasticeri','ushqime-baze','pije','snack-embelsira','produkte-shtepie','pije-alkoolike','produkte-te-ngrira','kafe-caj','kujdes-personal','produkte-per-bebe','produkte-per-kafshe');
