# DEPLOYMENT — production, backup and security checklist

## 1. Server
- Python 3.11+ on Linux (recommended) or Windows Server.
- Run with **Waitress** (`python run.py --prod`, or `ENESAI_ENV=production python run.py`). **Never** expose the Flask development server.
- Put a reverse proxy with **HTTPS** in front (Caddy/nginx/IIS). HTTPS is mandatory: browsers only allow GPS (`navigator.geolocation`) on HTTPS, and session cookies are `Secure` in production.
- One Waitress process (threads=8) is the supported layout: login rate limiting is in-process and SQLite is local. For several processes, use a shared rate-limit store first.
- If the proxy terminates TLS, wrap the app with Werkzeug `ProxyFix` (one trusted hop) so client IPs in the audit log/lockout are correct:
  ```python
  from werkzeug.middleware.proxy_fix import ProxyFix
  app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
  ```
  (add this in `run.py` only behind a proxy you control).

### Example (Linux, systemd + Caddy)
```
# /etc/systemd/system/enesai.service
[Service]
WorkingDirectory=/srv/enesai
EnvironmentFile=/srv/enesai/.env
ExecStart=/srv/enesai/.venv/bin/python run.py --prod
User=enesai
Restart=always
```
```
# Caddyfile
www.enesai.al {
  reverse_proxy 127.0.0.1:5000
}
```

## 2. Environment (`.env`, never in git)
`ENESAI_ENV=production`, `ENESAI_HTTPS=true`, a long random `SECRET_KEY`, `PUBLIC_BASE_URL=https://…`. Optional: `ADMIN_PATH` (obscurity only), `MAP_TILE_URL` (production tile provider), WhatsApp API keys. Rotating `SECRET_KEY` logs everyone out and empties carts.

## 3. Files and permissions
- `instance/enesai.sqlite3` — the database (orders, customers, settings).
- `instance/uploads/` — public images (served read-only at `/media/…`, images re-encoded by Pillow).
- `instance/private/invoices/`, `instance/private/imports/` — **private**; never served directly (PDFs only through signed customer links or the authenticated admin).
- Owner of `instance/` = the service user only (`chmod 700 instance`). The web server must not serve `instance/` as static files.

## 4. Backup and restore
SQLite runs in WAL mode; use the online backup API (safe while running):
```bash
# daily, keep 30 days (cron)
sqlite3 /srv/enesai/instance/enesai.sqlite3 ".backup '/backup/enesai-$(date +%F).sqlite3'"
tar czf /backup/enesai-files-$(date +%F).tgz -C /srv/enesai/instance uploads private
find /backup -name 'enesai-*' -mtime +30 -delete
```
Windows: `python -c "import sqlite3;s=sqlite3.connect('instance/enesai.sqlite3');d=sqlite3.connect('backup.sqlite3');s.backup(d)"` + copy `instance\uploads` and `instance\private`.

**Restore:** stop the service → copy the backup to `instance/enesai.sqlite3` (delete stale `-wal`/`-shm` files) → restore `uploads/` and `private/` → start. Test a restore at least once before launch. Keep backups encrypted/off-site: they contain customer data.

Before “Fshi të gjitha produktet” the admin offers a catalogue CSV download; a database backup is still recommended.

## 5. Updates
`git pull` → `pip install -r requirements.txt` → restart. Migrations in `enesai/migrations/` run automatically at start (forward-only, each in a transaction). Back up first.

## 6. Security checklist (go-live)
- [ ] HTTPS everywhere; HSTS on (automatic with `ENESAI_HTTPS=true`).
- [ ] `SECRET_KEY` set, long, random, not in git.
- [ ] Owner account created with `run.py create-owner`; strong password; no shared accounts.
- [ ] Operators have only the sections they need; Kuponat only for Managers.
- [ ] Demo data removed: `python seed.py --purge-demo`; dashboard no longer says “përmban të dhëna demonstrative”.
- [ ] Settings complete: legal name, NIPT, WhatsApp number, address, phones, hours, delivery fee/threshold (confirmed with the market).
- [ ] `/kushtet` text reviewed by a lawyer/accountant; the “tekst model” alert removed only after review (template `pages/kushtet.html`).
- [ ] Production map tile provider configured (`MAP_TILE_URL`), attribution correct, CSP allows that host (automatic).
- [ ] Backups scheduled and one restore tested.
- [ ] Admin login lockout tested (6 failures → 15 min) and audit log visible in “Regjistri”.
- [ ] Real-device tests: GPS on Android/iOS, WhatsApp with a long prefilled text, PDF printing.
- [ ] `ADULT_CHECKOUT_ENABLED` stays `false` until alcohol rules are confirmed.
- [ ] Card payment stays disabled until a licensed provider is integrated (never collect card data in this app).

## 7. Privacy notes
- Location is collected only after the customer presses “Përdor vendndodhjen time” or confirms a map pin; it is stored with the order for delivery and invoicing. Define a retention period with the market (orders must be kept as long as tax law requires; consider anonymising old orders’ coordinates/phones after that period).
- Logs (`audit_log`, server log) contain order numbers and staff actions, not passwords, tokens or full customer records. Customer-triggered events store no IP.
- The confirmation/PDF link contains a random 192-bit token (only its SHA-256 is stored) and expires after `ORDER_LINK_DAYS`.
