-- pragma: foreign_keys=off
-- Market product lists arrive before prices/categories are known (ARTIKUJ_TOTAL.xlsx: Kodi,
-- Përshkrimi, Njësi). Such products may be stored, but ONLY hidden: the CHECK below makes it
-- impossible for a product without a price or a category to be visible (and so orderable).
-- auto_hidden = 1 → hidden by the system only because data was missing; an import that later
-- completes price + category makes it visible again. A manual “Fshih” sets it to 0.
CREATE TABLE products_new (
  id              INTEGER PRIMARY KEY,
  sku             TEXT NOT NULL UNIQUE,
  name_sq         TEXT NOT NULL,
  name_en         TEXT NOT NULL DEFAULT '',
  desc_sq         TEXT NOT NULL DEFAULT '',
  desc_en         TEXT NOT NULL DEFAULT '',
  brand           TEXT NOT NULL DEFAULT '',
  packaging       TEXT NOT NULL DEFAULT '',
  unit            TEXT NOT NULL DEFAULT 'copë',
  barcode         TEXT NOT NULL DEFAULT '',
  price           INTEGER NOT NULL DEFAULT 0 CHECK (price >= 0),
  discount_pct    INTEGER NOT NULL DEFAULT 0 CHECK (discount_pct IN (0,5,10,15,20,25,30,40,50)),
  sale_price      INTEGER NOT NULL DEFAULT 0,
  stock           INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  low_threshold   INTEGER NOT NULL DEFAULT 5 CHECK (low_threshold >= 0),
  allow_backorder INTEGER NOT NULL DEFAULT 0,
  visible         INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0,1)),
  auto_hidden     INTEGER NOT NULL DEFAULT 0 CHECK (auto_hidden IN (0,1)),
  on_offers       INTEGER NOT NULL DEFAULT 1,
  category_id     INTEGER REFERENCES categories(id) ON DELETE RESTRICT,
  subcategory_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  search_text     TEXT NOT NULL DEFAULT '',
  is_demo         INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  CHECK (visible = 0 OR (price > 0 AND category_id IS NOT NULL))
);
INSERT INTO products_new(id, sku, name_sq, name_en, desc_sq, desc_en, brand, packaging, unit, barcode, price, discount_pct, sale_price, stock,
  low_threshold, allow_backorder, visible, auto_hidden, on_offers, category_id, subcategory_id, search_text, is_demo, created_at, updated_at)
SELECT id, sku, name_sq, name_en, desc_sq, desc_en, brand, packaging, unit, barcode, price, discount_pct, sale_price, stock,
  low_threshold, allow_backorder, visible, 0, on_offers, category_id, subcategory_id, search_text, is_demo, created_at, updated_at FROM products;
DROP TABLE IF EXISTS products_fts;
DROP TABLE products;
ALTER TABLE products_new RENAME TO products;
CREATE INDEX ix_products_cat ON products(category_id, visible);
CREATE INDEX ix_products_sub ON products(subcategory_id, visible);
CREATE INDEX ix_products_visible_disc ON products(visible, discount_pct);
CREATE INDEX ix_products_name ON products(name_sq);
CREATE INDEX ix_products_price ON products(sale_price);
CREATE INDEX ix_products_updated ON products(updated_at);
CREATE INDEX ix_products_barcode ON products(barcode);
