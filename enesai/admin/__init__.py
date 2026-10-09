"""Admin blueprint (prefix ADMIN_PATH, default /paneli). Every route is wrapped in
login_required / requires(section) — the sidebar only mirrors those rules."""
from flask import Blueprint, url_for

from ..db import get_db
from ..services import auth

bp = Blueprint("admin", __name__, template_folder="../templates")

NAV = [
    ("dash", "Dashboard", "layout-dashboard", "dashboard", None, None),
    ("ops", "Operatorët", "user-cog", "operators", "Menaxhimi", "operators"),
    ("prod", "Produktet", "package", "products", None, "products"),
    ("cats", "Kategoritë", "folder-tree", "categories_admin", None, "categories"),
    ("orders", "Porositë", "clipboard-list", "orders", None, "orders"),
    ("invoices", "Faturat", "receipt-text", "invoices", None, "invoices"),
    ("subs", "Abonentët", "users", "subscribers", "Marketingu", "subscribers"),
    ("mail", "Ofertat e Email-it", "send", "email_offers", None, "email"),
    ("coupons", "Kuponat", "ticket-percent", "coupons_page", None, "coupons"),
    ("ads", "Reklamat & Njoftimet", "megaphone", "ads", None, "ads"),
    ("reports", "Raportet", "chart-column", "reports", "Sistemi", "reports"),
    ("audit", "Regjistri i Veprimeve", "history", "audit_page", None, "audit"),
    ("settings", "Cilësimet", "settings", "settings", None, "settings"),
]


@bp.app_context_processor
def _admin_ctx():
    op = auth.current_operator()
    if not op:
        return {"can": lambda s: False, "op": None}
    new_orders = get_db().execute("SELECT COUNT(*) FROM orders WHERE status='new'").fetchone()[0] if auth.can("orders", op) else 0
    items, pending_group = [], None
    for key, label, ic, ep, group, perm in NAV:
        pending_group = group or pending_group
        allowed = perm is None or auth.can(perm, op)
        # operators see Kuponat with a lock (design: locked panel), everything else only when allowed
        if not allowed and not (perm == "coupons" and op["role"] == "operator"):
            continue
        items.append({"key": key, "label": label, "icon": ic, "url": url_for("admin." + ep), "allowed": allowed,
                      "group": pending_group, "badge": new_orders if key == "orders" and new_orders else None})
        pending_group = None
    return {"op": op, "can": lambda s: auth.can(s, op), "admin_nav": items, "new_orders": new_orders}


from . import views_core, views_catalog, views_orders, views_marketing  # noqa: E402,F401
