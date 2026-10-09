"""Append-only audit log writer (DB triggers forbid UPDATE/DELETE on audit_log).
Never write passwords, tokens or full customer records here — only identifiers."""
from flask import g, has_request_context

from ..db import get_db
from ..util import now_iso


def log(action, obj="", before="", after="", area="", tone="neutral", con=None, operator=None):
    con = con or get_db()
    op = operator
    if op is None and has_request_context():
        op = g.get("operator")
    ip = ""
    if op and has_request_context():  # staff actions keep the IP; customer-triggered system events do not
        from ..security import client_ip
        ip = client_ip()
    con.execute(
        "INSERT INTO audit_log(at, operator_id, operator_name, action, area, object, before, after, ip, tone) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (now_iso(), op["id"] if op else None, op["name"] if op else "Sistemi", action, area, str(obj)[:400],
         str(before)[:400], str(after)[:400], ip, tone))
