"""SQLite access + forward-only schema migrations.

Every connection: foreign keys ON, WAL journal, busy timeout. Money is stored as
whole lek (INTEGER). Times are stored as local Europe/Tirane ISO strings
(`YYYY-MM-DDTHH:MM:SS`), which is what every screen shows.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    try:
        con.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError:
        pass
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


@contextmanager
def transaction(con=None, immediate=True):
    """Explicit transaction. IMMEDIATE takes the write lock up front so concurrent
    writers (orders, coupon use, counters) are serialised by SQLite itself."""
    con = con or get_db()
    con.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def query(sql, args=(), one=False, con=None):
    cur = (con or get_db()).execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def scalar(sql, args=(), con=None, default=None):
    row = (con or get_db()).execute(sql, args).fetchone()
    return row[0] if row and row[0] is not None else default


def fts_available(con):
    try:
        con.execute("SELECT 1 FROM products_fts LIMIT 1")
        return True
    except sqlite3.OperationalError:
        return False


def migrate(con):
    """Apply migrations/NNNN_*.sql in order, each in its own transaction.
    Optional FTS5 index is created afterwards when the SQLite build supports it."""
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
    done = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
    applied = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        ver = f.stem
        if ver in done:
            continue
        sql = f.read_text(encoding="utf-8")
        con.execute("BEGIN IMMEDIATE")
        try:
            for stmt in _split_sql(sql):
                con.execute(stmt)
            con.execute("INSERT INTO schema_migrations(version) VALUES (?)", (ver,))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        applied.append(ver)
    _ensure_fts(con)
    return applied


def _ensure_fts(con):
    if fts_available(con):
        return
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("CREATE VIRTUAL TABLE products_fts USING fts5(search_text, content='products', content_rowid='id', tokenize='unicode61 remove_diacritics 2')")
        con.execute("CREATE TRIGGER products_fts_ai AFTER INSERT ON products BEGIN INSERT INTO products_fts(rowid, search_text) VALUES (new.id, new.search_text); END")
        con.execute("CREATE TRIGGER products_fts_ad AFTER DELETE ON products BEGIN INSERT INTO products_fts(products_fts, rowid, search_text) VALUES ('delete', old.id, old.search_text); END")
        con.execute("CREATE TRIGGER products_fts_au AFTER UPDATE OF search_text ON products BEGIN INSERT INTO products_fts(products_fts, rowid, search_text) VALUES ('delete', old.id, old.search_text); INSERT INTO products_fts(rowid, search_text) VALUES (new.id, new.search_text); END")
        con.execute("INSERT INTO products_fts(products_fts) VALUES ('rebuild')")
        con.execute("COMMIT")
    except sqlite3.OperationalError:
        con.execute("ROLLBACK")  # FTS5 not compiled in: search falls back to LIKE


def _split_sql(sql):
    """Split on ';' at line ends, keeping CREATE TRIGGER ... END; blocks whole."""
    out, buf, in_trigger = [], [], False
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        up = s.upper()
        if up.startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if up.endswith("END;"):
                out.append("\n".join(buf)); buf = []; in_trigger = False
        elif s.endswith(";"):
            out.append("\n".join(buf)); buf = []
    if buf:
        out.append("\n".join(buf))
    return out
