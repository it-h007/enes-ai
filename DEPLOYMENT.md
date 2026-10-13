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
`ENESAI_ENV=production`, `ENESAI_HTTPS=true`, a long random `SECRET_KEY`, `PUBLIC_BASE_URL=https://…`. Leave `ADMIN_PATH` empty: a random secret admin path is created once in `instance/admin_path` (print it with `python run.py admin-url`); easy guesses are ignored. Optional: `MAP_TILE_URL` (production tile provider), WhatsApp API keys. Rotating `SECRET_KEY` logs everyone out and empties carts.

`chmod 600 .env` and `chmod 700 instance` — only the service user may read them (the app warns at start-up otherwise). The reverse proxy must only forward to the app; never point a web server's document root at the project folder.

## 3. Files and permissions
- `instance/enesai.sqlite3` — the database (orders, customers, settings).
- `instance/uploads/` — public images (served read-only at `/media/…`, images re-encoded by Pillow).
- `instance/private/invoices/`, `instance/private/imports/` — **private**; never served directly (PDFs only through signed customer links or the authenticated admin).
- Owner of `instance/` = the service user only (`chmod 700 instance`). The web server must not serve `instance/` as static files.

## 4. Backup and restore
**Automatic:** while `run.py` runs it creates one ZIP per day in `instance/backups/` (consistent SQLite copy via the online backup API + uploads + invoice PDFs) and keeps `BACKUP_KEEP_DAYS` (30, always at least the 7 newest). Manual: `python run.py backup`.

**Off-site copy (required):** a backup on the same server does not survive a lost server. Sync the folder every night with `rclone` to a storage bucket (e.g. Backblaze B2) or Google Drive:
```bash
# once: rclone config  (create remote "offsite")
# cron, 03:30 every night
30 3 * * * rclone copy /srv/enesai/instance/backups offsite:enesai-backups --max-age 48h
```

Manual alternative (SQLite CLI):
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

## 4b. Firewall and brute-force protection
```bash
ufw default deny incoming && ufw allow OpenSSH && ufw allow 80,443/tcp && ufw enable
apt install fail2ban
```
`/etc/fail2ban/filter.d/enesai.conf`:
```
[Definition]
failregex = admin login failed ip=<HOST>$
            bot trap: \S+ from <HOST>$
```
`/etc/fail2ban/jail.d/enesai.conf` (log = the service journal, or redirect run.py output to a file):
```
[enesai]
enabled  = true
backend  = systemd
journalmatch = _SYSTEMD_UNIT=enesai.service
filter   = enesai
maxretry = 10
findtime = 10m
bantime  = 1h
```
SSH: key login only (`PasswordAuthentication no`). Keep the OS updated (`unattended-upgrades`).

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
- [ ] Daily backups appear in `instance/backups/`, the off-site copy (rclone) works, and one restore was tested.
- [ ] Admin address printed with `python run.py admin-url` and saved by the owner; `/admin` and `/paneli` return 404.
- [ ] `ufw` + `fail2ban` active; `.env` is `chmod 600`.
- [ ] Admin login lockout tested (6 failures → 15 min) and audit log visible in “Regjistri”.
- [ ] Real-device tests: GPS on Android/iOS, WhatsApp with a long prefilled text, PDF printing.
- [ ] `ADULT_CHECKOUT_ENABLED` stays `false` until alcohol rules are confirmed.
- [ ] Card payment stays disabled until a licensed provider is integrated (never collect card data in this app).

## 7. Privacy notes
- Location is collected only after the customer presses “Përdor vendndodhjen time” or confirms a map pin; it is stored with the order for delivery and invoicing. Define a retention period with the market (orders must be kept as long as tax law requires; consider anonymising old orders’ coordinates/phones after that period).
- Logs (`audit_log`, server log) contain order numbers and staff actions, not passwords, tokens or full customer records. Customer-triggered events store no IP.
- The confirmation/PDF link contains a random 192-bit token (only its SHA-256 is stored) and expires after `ORDER_LINK_DAYS`.
