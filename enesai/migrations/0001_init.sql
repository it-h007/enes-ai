-- ENES'AI SUPER MARKET — initial schema (CODEX_IMPLEMENTATION_MAP §6, extended)
-- Money: INTEGER whole lek. Times: local Europe/Tirane ISO 'YYYY-MM-DDTHH:MM:SS'.

CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE categories (
  id         INTEGER PRIMARY KEY,
  slug       TEXT NOT NULL UNIQUE,
  name_sq    TEXT NOT NULL,
  name_en    TEXT NOT NULL DEFAULT '',
  parent_id  INTEGER REFERENCES categories(id) ON DELETE RESTRICT,
  image      TEXT NOT NULL DEFAULT '',
  sort       INTEGER NOT NULL DEFAULT 0,
  visible    INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0,1)),
  adult      INTEGER NOT NULL DEFAULT 0 CHECK (adult IN (0,1)),
  is_demo    INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX ix_categories_parent ON categories(parent_id, sort);

CREATE TABLE products (
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
  price           INTEGER NOT NULL CHECK (price > 0),
  discount_pct    INTEGER NOT NULL DEFAULT 0 CHECK (discount_pct IN (0,5,10,15,20,25,30,40,50)),
  sale_price      INTEGER NOT NULL DEFAULT 0, -- price after discount_pct, maintained by the app
  stock           INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
  low_threshold   INTEGER NOT NULL DEFAULT 5 CHECK (low_threshold >= 0),
  allow_backorder INTEGER NOT NULL DEFAULT 0,
  visible         INTEGER NOT NULL DEFAULT 1 CHECK (visible IN (0,1)),
  on_offers       INTEGER NOT NULL DEFAULT 1,
  category_id     INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
  subcategory_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  search_text     TEXT NOT NULL DEFAULT '',
  is_demo         INTEGER NOT NULL DEFAULT 0,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX ix_products_cat ON products(category_id, visible);
CREATE INDEX ix_products_sub ON products(subcategory_id, visible);
CREATE INDEX ix_products_visible_disc ON products(visible, discount_pct);
CREATE INDEX ix_products_name ON products(name_sq);
CREATE INDEX ix_products_price ON products(sale_price);
CREATE INDEX ix_products_updated ON products(updated_at);

CREATE TABLE product_images (
  id         INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  path       TEXT NOT NULL,
  sort       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_product_images ON product_images(product_id, sort);

CREATE TABLE operators (
  id                   INTEGER PRIMARY KEY,
  name                 TEXT NOT NULL,
  username             TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash        TEXT NOT NULL,
  role                 TEXT NOT NULL CHECK (role IN ('owner','manager','operator')),
  active               INTEGER NOT NULL DEFAULT 1,
  must_change_password INTEGER NOT NULL DEFAULT 1,
  last_login_at        TEXT,
  last_activity_at     TEXT,
  created_at           TEXT NOT NULL
);
-- exactly one owner
CREATE UNIQUE INDEX ux_single_owner ON operators(role) WHERE role = 'owner';

CREATE TABLE operator_permissions (
  operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  section     TEXT NOT NULL,
  PRIMARY KEY (operator_id, section)
);

CREATE TABLE admin_sessions (
  id          TEXT PRIMARY KEY,
  operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  last_seen   TEXT NOT NULL,
  ip          TEXT NOT NULL DEFAULT '',
  user_agent  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE login_attempts (
  id       INTEGER PRIMARY KEY,
  username TEXT NOT NULL COLLATE NOCASE,
  ip       TEXT NOT NULL,
  at       TEXT NOT NULL,
  success  INTEGER NOT NULL
);
CREATE INDEX ix_login_attempts ON login_attempts(username, ip, at);

CREATE TABLE audit_log (
  id            INTEGER PRIMARY KEY,
  at            TEXT NOT NULL,
  operator_id   INTEGER,
  operator_name TEXT NOT NULL DEFAULT 'Sistemi',
  action        TEXT NOT NULL,
  area          TEXT NOT NULL DEFAULT '',
  object        TEXT NOT NULL DEFAULT '',
  before        TEXT NOT NULL DEFAULT '',
  after         TEXT NOT NULL DEFAULT '',
  ip            TEXT NOT NULL DEFAULT '',
  tone          TEXT NOT NULL DEFAULT 'neutral'
);
CREATE INDEX ix_audit_at ON audit_log(at);
CREATE INDEX ix_audit_op ON audit_log(operator_id, at);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE order_counters (
  prefix TEXT NOT NULL,
  year   INTEGER NOT NULL,
  last   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (prefix, year)
);

CREATE TABLE orders (
  id                INTEGER PRIMARY KEY,
  nr                TEXT NOT NULL UNIQUE,
  created_at        TEXT NOT NULL,
  name              TEXT NOT NULL,
  surname           TEXT NOT NULL,
  phone             TEXT NOT NULL,
  phone_digits      TEXT NOT NULL,
  email             TEXT NOT NULL DEFAULT '',
  marketing_optin   INTEGER NOT NULL DEFAULT 0,
  optin_at          TEXT,
  city              TEXT NOT NULL DEFAULT 'Vlorë',
  zone              TEXT NOT NULL DEFAULT '',
  address           TEXT NOT NULL,
  courier_note      TEXT NOT NULL DEFAULT '',
  lat               REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
  lng               REAL NOT NULL CHECK (lng BETWEEN -180 AND 180),
  loc_source        TEXT NOT NULL CHECK (loc_source IN ('gps','map')),
  accuracy_m        INTEGER,
  items_count       INTEGER NOT NULL,
  subtotal          INTEGER NOT NULL,
  coupon_code       TEXT,
  coupon_pct        INTEGER NOT NULL DEFAULT 0,
  discount          INTEGER NOT NULL DEFAULT 0,
  delivery          INTEGER NOT NULL DEFAULT 0,
  total             INTEGER NOT NULL,
  payment           TEXT NOT NULL DEFAULT 'cash' CHECK (payment IN ('cash')),
  status            TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','prep','route','done','cancel')),
  status_changed_at TEXT,
  wa_opened_at      TEXT,
  wa_sent_at        TEXT,
  wa_message_id     TEXT,
  wa_status         TEXT NOT NULL DEFAULT '',
  pdf_path          TEXT NOT NULL DEFAULT '',
  seller_snapshot   TEXT NOT NULL,
  access_token_hash TEXT NOT NULL,
  idempotency_key   TEXT NOT NULL UNIQUE,
  search_norm       TEXT NOT NULL DEFAULT '',
  is_demo           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX ix_orders_created ON orders(created_at);
CREATE INDEX ix_orders_status ON orders(status, created_at);
CREATE INDEX ix_orders_phone ON orders(phone_digits);
CREATE INDEX ix_orders_email ON orders(email);
CREATE INDEX ix_orders_coupon ON orders(coupon_code);

CREATE TABLE order_items (
  id         INTEGER PRIMARY KEY,
  order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
  sku        TEXT NOT NULL,
  name       TEXT NOT NULL,
  pack       TEXT NOT NULL DEFAULT '',
  image      TEXT NOT NULL DEFAULT '',
  unit_price INTEGER NOT NULL,
  list_price INTEGER NOT NULL,
  discount_pct INTEGER NOT NULL DEFAULT 0,
  qty        INTEGER NOT NULL CHECK (qty > 0)
);
CREATE INDEX ix_order_items_order ON order_items(order_id);
CREATE INDEX ix_order_items_product ON order_items(product_id);

CREATE TABLE coupons (
  code            TEXT PRIMARY KEY,
  pct             INTEGER NOT NULL CHECK (pct BETWEEN 1 AND 90),
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','used','cancelled')),
  created_by      INTEGER REFERENCES operators(id) ON DELETE SET NULL,
  created_by_name TEXT NOT NULL DEFAULT '',
  created_at      TEXT NOT NULL,
  ends_on         TEXT,
  note            TEXT NOT NULL DEFAULT '',
  used_order_nr   TEXT,
  used_by         TEXT,
  used_at         TEXT,
  cancelled_at    TEXT,
  is_demo         INTEGER NOT NULL DEFAULT 0,
  CHECK (code = upper(code) AND length(code) BETWEEN 4 AND 20)
);
CREATE INDEX ix_coupons_status ON coupons(status);

CREATE TABLE coupon_events (
  id       INTEGER PRIMARY KEY,
  code     TEXT NOT NULL REFERENCES coupons(code) ON DELETE CASCADE,
  event    TEXT NOT NULL CHECK (event IN ('created','used','returned','cancelled')),
  order_nr TEXT,
  at       TEXT NOT NULL,
  by_name  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX ix_coupon_events ON coupon_events(code, at);

CREATE TABLE subscribers (
  id              INTEGER PRIMARY KEY,
  email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
  created_at      TEXT NOT NULL,
  source          TEXT NOT NULL DEFAULT 'ballina',
  active          INTEGER NOT NULL DEFAULT 1,
  unsubscribed_at TEXT,
  token           TEXT NOT NULL UNIQUE,
  is_demo         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE email_campaigns (
  id          INTEGER PRIMARY KEY,
  subject     TEXT NOT NULL,
  intro       TEXT NOT NULL DEFAULT '',
  button_text TEXT NOT NULL DEFAULT 'Shiko ofertat',
  product_ids TEXT NOT NULL DEFAULT '[]',
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','prepared','sent')),
  created_by  TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL,
  prepared_at TEXT,
  sent_at     TEXT,
  recipients  INTEGER
);

CREATE TABLE announcements (
  id           INTEGER PRIMARY KEY,
  type         TEXT NOT NULL CHECK (type IN ('njoftim','reklame','pune')),
  title_sq     TEXT NOT NULL,
  title_en     TEXT NOT NULL DEFAULT '',
  summary_sq   TEXT NOT NULL DEFAULT '',
  summary_en   TEXT NOT NULL DEFAULT '',
  body_sq      TEXT NOT NULL DEFAULT '',
  body_en      TEXT NOT NULL DEFAULT '',
  image        TEXT NOT NULL DEFAULT '',
  image_contain INTEGER NOT NULL DEFAULT 0,
  link         TEXT NOT NULL DEFAULT '',
  link_label   TEXT NOT NULL DEFAULT '',
  starts_at    TEXT,
  ends_at      TEXT,
  published    INTEGER NOT NULL DEFAULT 1,
  on_home      INTEGER NOT NULL DEFAULT 0,
  sort         INTEGER NOT NULL DEFAULT 0,
  job_position TEXT NOT NULL DEFAULT '',
  job_schedule TEXT NOT NULL DEFAULT '',
  job_place    TEXT NOT NULL DEFAULT '',
  job_deadline TEXT NOT NULL DEFAULT '',
  is_demo      INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL,
  updated_at   TEXT NOT NULL
);
CREATE INDEX ix_announcements_pub ON announcements(published, on_home, sort);

CREATE TABLE import_jobs (
  id             INTEGER PRIMARY KEY,
  filename       TEXT NOT NULL,
  created_by     TEXT NOT NULL DEFAULT '',
  created_at     TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'preview' CHECK (status IN ('preview','running','done','failed','discarded')),
  total          INTEGER NOT NULL DEFAULT 0,
  done_rows      INTEGER NOT NULL DEFAULT 0,
  created_n      INTEGER NOT NULL DEFAULT 0,
  updated_n      INTEGER NOT NULL DEFAULT 0,
  warnings       INTEGER NOT NULL DEFAULT 0,
  errors         INTEGER NOT NULL DEFAULT 0,
  auto_categories INTEGER NOT NULL DEFAULT 1,
  payload_path   TEXT NOT NULL DEFAULT '',
  error_csv_path TEXT NOT NULL DEFAULT '',
  finished_at    TEXT
);

CREATE TABLE wa_outbox (
  id         INTEGER PRIMARY KEY,
  order_id   INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  attempt    INTEGER NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed')),
  error      TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  sent_at    TEXT
);
