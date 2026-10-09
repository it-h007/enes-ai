"""Optional automatic invoice delivery through the WhatsApp Business Cloud API (C-03).

DISABLED unless WA_TOKEN, WA_PHONE_ID and WA_TEMPLATE are set in the environment AND
Settings › “Automatikisht” is chosen. Nothing here is simulated: an order is only marked
as sent (wa_sent_at, wa_message_id) after Meta's API accepts the message. On failure the
order keeps the manual button and staff see “Pa dërguar” in the admin.

Flow: upload the PDF to /<PHONE_ID>/media → send an approved template message whose header
is the document → store the message id. Requires a verified Meta Business account, a sender
number and an approved template with a DOCUMENT header and one body variable (order number).
"""
import json
import threading
import time
import urllib.request
import uuid

from flask import current_app

from ..db import connect
from ..util import now_iso
from . import invoice_pdf
from . import settings as st
from .orders import market_wa_digits

GRAPH = "https://graph.facebook.com"


def queue_send(order_id):
    app = current_app._get_current_object()
    if not (app.config.get("WA_TOKEN") and app.config.get("WA_PHONE_ID") and app.config.get("WA_TEMPLATE")):
        return False
    threading.Thread(target=_worker, args=(app, order_id), daemon=True).start()
    return True


def _worker(app, order_id, attempts=3):
    with app.app_context():
        con = connect(app.config["DATABASE"])
        try:
            for attempt in range(1, attempts + 1):
                con.execute("INSERT INTO wa_outbox(order_id, attempt, status, created_at) VALUES (?,?, 'pending', ?)", (order_id, attempt, now_iso()))
                box_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
                try:
                    msg_id = send_invoice(con, order_id)
                    t = now_iso()
                    con.execute("UPDATE orders SET wa_sent_at=?, wa_message_id=?, wa_status='api_sent' WHERE id=?", (t, msg_id, order_id))
                    con.execute("UPDATE wa_outbox SET status='sent', sent_at=? WHERE id=?", (t, box_id))
                    return
                except Exception as e:  # network/API errors: retry with back-off, never pretend success
                    con.execute("UPDATE wa_outbox SET status='failed', error=? WHERE id=?", (str(e)[:300], box_id))
                    app.logger.warning("WhatsApp API send failed for order %s (attempt %d): %s", order_id, attempt, str(e)[:200])
                    time.sleep(2 ** attempt)
            con.execute("UPDATE orders SET wa_status='api_failed' WHERE id=?", (order_id,))
        finally:
            con.close()


def _request(url, data=None, headers=None, method="POST"):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def send_invoice(con, order_id):
    cfg = current_app.config
    o = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    to = market_wa_digits(o)
    if not to:
        raise RuntimeError("market WhatsApp number missing")
    path = invoice_pdf.ensure_pdf(o, con)
    auth = {"Authorization": "Bearer " + cfg["WA_TOKEN"]}
    boundary = uuid.uuid4().hex
    body = b"".join([
        b"--" + boundary.encode() + b"\r\nContent-Disposition: form-data; name=\"messaging_product\"\r\n\r\nwhatsapp\r\n",
        b"--" + boundary.encode() + b"\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\napplication/pdf\r\n",
        b"--" + boundary.encode() + ("\r\nContent-Disposition: form-data; name=\"file\"; filename=\"Fatura-%s.pdf\"\r\nContent-Type: application/pdf\r\n\r\n" % o["nr"]).encode(),
        path.read_bytes(), b"\r\n--" + boundary.encode() + b"--\r\n"])
    media = _request("%s/%s/%s/media" % (GRAPH, cfg["WA_API_VERSION"], cfg["WA_PHONE_ID"]), body,
                     dict(auth, **{"Content-Type": "multipart/form-data; boundary=" + boundary}))
    msg = {"messaging_product": "whatsapp", "to": to, "type": "template",
           "template": {"name": cfg["WA_TEMPLATE"], "language": {"code": cfg["WA_TEMPLATE_LANG"]},
                        "components": [{"type": "header", "parameters": [{"type": "document", "document": {"id": media["id"], "filename": "Fatura-%s.pdf" % o["nr"]}}]},
                                       {"type": "body", "parameters": [{"type": "text", "text": o["nr"]}]}]}}
    res = _request("%s/%s/%s/messages" % (GRAPH, cfg["WA_API_VERSION"], cfg["WA_PHONE_ID"]), json.dumps(msg).encode(),
                   dict(auth, **{"Content-Type": "application/json"}))
    return res["messages"][0]["id"]
