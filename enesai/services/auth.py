"""Admin authentication, sessions, roles and permissions.

- Passwords: Werkzeug scrypt (salted per hash). No default/demo password exists anywhere:
  the owner is created once with `python run.py create-owner` (or the first-run setup page,
  which only works while no owner exists and only from localhost).
- Lockout: LOGIN_MAX_FAILURES failures for the same username+IP within LOGIN_LOCK_MINUTES
  lock that pair for LOGIN_LOCK_MINUTES (default 6 → 15 min); plus an IP-wide limit.
- Sessions: a random id stored server-side (admin_sessions) — logout, deactivation and
  “end other sessions” revoke immediately; idle timeout from Settings (30 min / 1 h / 8 h).
- Authorisation: Owner = everything, always. Manager/Operator = ticked sections.
  ‘coupons’ can only be granted to Managers (CR-17 / C-07). ‘operators’ and
  ‘products_delete_all’ are Owner-only and are not grantable.
"""
import secrets
from datetime import timedelta
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db, transaction
from ..util import now, now_iso, parse_dt
from . import audit
from . import settings as st

# (key, label shown in the permission matrix)
SECTIONS = [
    ("orders", "Porositë"), ("invoices", "Faturat"), ("products", "Produktet"), ("import", "Importi CSV"),
    ("categories", "Kategoritë"), ("subscribers", "Abonentët"), ("email", "Ofertat e email-it"), ("coupons", "Kuponat"),
    ("ads", "Reklamat & Njoftimet"), ("reports", "Raportet"), ("audit", "Regjistri"), ("settings", "Cilësimet"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]
OWNER_ONLY = ("operators", "products_delete_all")
ROLE_LABEL = {"owner": "Pronar", "manager": "Menaxher/e", "operator": "Operator/e"}
_DUMMY_HASH = generate_password_hash("not-a-real-password-" + secrets.token_hex(8))
MIN_PW = 10


def hash_password(pw):
    return generate_password_hash(pw)


def password_problem(pw, username=""):
    if len(pw or "") < MIN_PW:
        return "Fjalëkalimi duhet të ketë të paktën %d shenja." % MIN_PW
    if username and username.lower() in pw.lower():
        return "Fjalëkalimi nuk duhet të përmbajë emrin e përdoruesit."
    if pw.isdigit() or pw.isalpha():
        return "Përdorni shkronja dhe shifra (ose shenja)."
    return None


def create_owner(username, name, password, con=None):
    con = con or get_db()
    username = (username or "").strip().lower()
    if con.execute("SELECT 1 FROM operators WHERE role='owner'").fetchone():
        return False, "Pronari ekziston tashmë. Ky veprim lejohet vetëm një herë."
    if not username or not username.replace(".", "").replace("_", "").isalnum():
        return False, "Emri i përdoruesit: vetëm shkronja, shifra, pikë ose _."
    prob = password_problem(password, username)
    if prob or len(password) < 12:
        return False, prob or "Për pronarin përdorni të paktën 12 shenja."
    con.execute("INSERT INTO operators(name, username, password_hash, role, active, must_change_password, created_at) VALUES (?,?,?, 'owner', 1, 0, ?)",
                (name.strip() or "Pronari", username, hash_password(password), now_iso()))
    audit.log("Krijoi pronarin", "@" + username, area="operators", tone="new", con=con, operator=False)
    return True, "Pronari u krijua. Hyni te %s/login" % current_app.config["ADMIN_PATH"]


def owner_exists(con=None):
    return bool((con or get_db()).execute("SELECT 1 FROM operators WHERE role='owner'").fetchone())


# ---------------- login / lockout ----------------

def _window_start():
    return (now() - timedelta(minutes=current_app.config["LOGIN_LOCK_MINUTES"])).isoformat(timespec="seconds")


def locked(username, ip, con=None):
    con = con or get_db()
    since = _window_start()
    last_ok = con.execute("SELECT MAX(at) FROM login_attempts WHERE username=? AND ip=? AND success=1", (username, ip)).fetchone()[0] or ""
    start = max(since, last_ok)
    fails = con.execute("SELECT COUNT(*) FROM login_attempts WHERE username=? AND ip=? AND success=0 AND at > ?", (username, ip, start)).fetchone()[0]
    ip_fails = con.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=? AND success=0 AND at > ?", (ip, since)).fetchone()[0]
    return fails >= current_app.config["LOGIN_MAX_FAILURES"] or ip_fails >= current_app.config["LOGIN_MAX_FAILURES"] * 5


def attempt(username, password, ip, ua=""):
    """Returns (operator_row, error_code). error_code ∈ locked | invalid | inactive."""
    con = get_db()
    username = (username or "").strip().lower()[:60]
    if locked(username, ip, con):
        audit.log("Hyrje e bllokuar", "@" + username, area="auth", tone="danger", con=con, operator=False)
        return None, "locked"
    row = con.execute("SELECT * FROM operators WHERE username = ?", (username,)).fetchone()
    ok = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password or "")
    if not row or not ok:
        con.execute("INSERT INTO login_attempts(username, ip, at, success) VALUES (?,?,?,0)", (username, ip, now_iso()))
        audit.log("Hyrje e dështuar", "@" + username, area="auth", tone="danger", con=con, operator=False)
        return None, ("locked" if locked(username, ip, con) else "invalid")
    if not row["active"]:
        con.execute("INSERT INTO login_attempts(username, ip, at, success) VALUES (?,?,?,0)", (username, ip, now_iso()))
        return None, "inactive"
    con.execute("INSERT INTO login_attempts(username, ip, at, success) VALUES (?,?,?,1)", (username, ip, now_iso()))
    sid = secrets.token_urlsafe(32)
    t = now_iso()
    con.execute("INSERT INTO admin_sessions(id, operator_id, created_at, last_seen, ip, user_agent) VALUES (?,?,?,?,?,?)",
                (sid, row["id"], t, t, ip, (ua or "")[:200]))
    con.execute("UPDATE operators SET last_login_at=?, last_activity_at=? WHERE id=?", (t, t, row["id"]))
    # keep the shopping cart, drop everything else (session fixation hygiene)
    cart = session.get("cart")
    session.clear()
    if cart:
        session["cart"] = cart
    session["admin_sid"] = sid
    session.permanent = True
    g.operator = operator_view(row, con)
    audit.log("Hyrje në panel", "—", area="auth", con=con)
    # old attempts cleanup (keeps the table small)
    con.execute("DELETE FROM login_attempts WHERE at < ?", ((now() - timedelta(days=30)).isoformat(timespec="seconds"),))
    return row, None


def logout():
    sid = session.pop("admin_sid", None)
    if sid:
        get_db().execute("DELETE FROM admin_sessions WHERE id = ?", (sid,))


def operator_view(row, con=None):
    con = con or get_db()
    perms = set(SECTION_KEYS) | set(OWNER_ONLY) if row["role"] == "owner" else \
        {r[0] for r in con.execute("SELECT section FROM operator_permissions WHERE operator_id=?", (row["id"],))}
    if row["role"] == "operator":
        perms.discard("coupons")  # never for operators, whatever is stored
    ini = "".join(w[0] for w in row["name"].split()[:2]).upper() or "?"
    return {"id": row["id"], "name": row["name"], "username": row["username"], "role": row["role"], "perms": perms, "ini": ini,
            "must_change": bool(row["must_change_password"]), "role_label": "Të gjitha lejet" if row["role"] == "owner" else ROLE_LABEL[row["role"]]}


def current_operator():
    if "operator" in g:
        return g.operator
    g.operator = None
    sid = session.get("admin_sid")
    if not sid:
        return None
    con = get_db()
    r = con.execute("""SELECT s.id AS sid, s.last_seen, o.* FROM admin_sessions s JOIN operators o ON o.id = s.operator_id
                       WHERE s.id = ?""", (sid,)).fetchone()
    if not r or not r["active"]:
        session.pop("admin_sid", None)
        return None
    timeout = st.int_setting("session_timeout", 30)
    last = parse_dt(r["last_seen"])
    if last is None or now() - last > timedelta(minutes=max(5, timeout)):
        con.execute("DELETE FROM admin_sessions WHERE id = ?", (sid,))
        session.pop("admin_sid", None)
        g.session_expired = True
        return None
    if (now() - last).total_seconds() > 30:
        con.execute("UPDATE admin_sessions SET last_seen=? WHERE id=?", (now_iso(), sid))
    g.operator = operator_view(r, con)
    return g.operator


def can(section, op=None):
    op = op or current_operator()
    return bool(op) and (op["role"] == "owner" or section in op["perms"])


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **k):
        op = current_operator()
        if not op:
            if request.headers.get("X-Requested-With") == "fetch":
                abort(401)
            return redirect(url_for("admin.login", next=request.full_path if request.method == "GET" else None))
        if op["must_change"] and request.endpoint not in ("admin.change_password", "admin.logout"):
            return redirect(url_for("admin.change_password"))
        return fn(*a, **k)
    return wrapper


def requires(section):
    """Server-side permission check on every admin route (hiding buttons is not security)."""
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **k):
            op = current_operator()
            if not can(section, op):
                audit.log("Akses i ndaluar", "%s %s" % (request.method, request.path), area=section, tone="danger")
                abort(403)
            return fn(*a, **k)
        return wrapper
    return deco


def end_other_sessions(op):
    get_db().execute("DELETE FROM admin_sessions WHERE operator_id = ? AND id <> ?", (op["id"], session.get("admin_sid", "")))


def change_password(op, current, new, confirm):
    con = get_db()
    row = con.execute("SELECT * FROM operators WHERE id=?", (op["id"],)).fetchone()
    if not check_password_hash(row["password_hash"], current or ""):
        return "Fjalëkalimi aktual nuk është i saktë."
    if new != confirm:
        return "Fjalëkalimet e reja nuk përputhen."
    prob = password_problem(new, row["username"])
    if prob:
        return prob
    if check_password_hash(row["password_hash"], new):
        return "Zgjidhni një fjalëkalim të ri, jo të njëjtin."
    with transaction(con):
        con.execute("UPDATE operators SET password_hash=?, must_change_password=0 WHERE id=?", (hash_password(new), op["id"]))
        con.execute("DELETE FROM admin_sessions WHERE operator_id = ? AND id <> ?", (op["id"], session.get("admin_sid", "")))
        audit.log("Ndryshoi fjalëkalimin", "@" + row["username"], area="auth", con=con)
    return None


def reset_password(username, new, con=None):
    """Local console recovery (run.py reset-password): sets a new password, clears the
    lockout for that username and ends all of its sessions. Returns an error text or None."""
    con = con or get_db()
    username = (username or "").strip().lower()
    row = con.execute("SELECT * FROM operators WHERE username=?", (username,)).fetchone()
    if not row:
        return "Nuk ekziston përdorues me këtë emër."
    prob = password_problem(new, username)
    if prob:
        return prob
    if row["role"] == "owner" and len(new) < 12:
        return "Për pronarin përdorni të paktën 12 shenja."
    with transaction(con):
        con.execute("UPDATE operators SET password_hash=?, must_change_password=0, active=1 WHERE id=?",
                    (hash_password(new), row["id"]))
        con.execute("DELETE FROM login_attempts WHERE username=?", (username,))
        con.execute("DELETE FROM admin_sessions WHERE operator_id=?", (row["id"],))
        audit.log("Rivendosi fjalëkalimin (konsolë)", "@" + username, area="auth", tone="danger", con=con, operator=False)
    return None
