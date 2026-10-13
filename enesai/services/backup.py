"""Daily backups: one ZIP with a consistent copy of the SQLite database (online backup API,
safe while the shop is running) + uploaded photos + invoice PDFs.

    python run.py backup            → make one now
    (automatic)                     → run.py starts a background check every hour and makes
                                      one backup per day; older than BACKUP_KEEP_DAYS are pruned

Copy the BACKUP_DIR folder off the server (DEPLOYMENT.md §4) — a backup on the same disk does
not survive a lost server."""
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

PREFIX = "enesai-backup-"


def backup_dir(app):
    d = Path(app.config["BACKUP_DIR"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_backup(app):
    d = backup_dir(app)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = d / ("%s%s.zip" % (PREFIX, stamp))
    tmp = Path(tempfile.mkdtemp()) / "enesai.sqlite3"
    src = sqlite3.connect(app.config["DATABASE"])
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    partial = target.with_suffix(".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "enesai.sqlite3")
        for folder, arc in ((Path(app.config["UPLOAD_DIR"]), "uploads"), (Path(app.config["PRIVATE_DIR"]) / "invoices", "private/invoices")):
            if folder.is_dir():
                for f in folder.rglob("*"):
                    if f.is_file():
                        z.write(f, "%s/%s" % (arc, f.relative_to(folder).as_posix()))
    partial.rename(target)
    tmp.unlink(missing_ok=True)
    tmp.parent.rmdir()
    prune(app)
    app.logger.info("backup created %s (%d KB)", target.name, target.stat().st_size // 1024)
    return target


def backups(app):
    return sorted(backup_dir(app).glob(PREFIX + "*.zip"))


def prune(app):
    keep_days = app.config.get("BACKUP_KEEP_DAYS", 30)
    files = backups(app)
    limit = time.time() - keep_days * 86400
    for f in files[:-7]:          # always keep the 7 newest, whatever their age
        if f.stat().st_mtime < limit:
            f.unlink(missing_ok=True)


def made_today(app):
    today = datetime.now().strftime("%Y-%m-%d")
    return any(f.name.startswith(PREFIX + today) for f in backups(app))


def start_daily(app, every_seconds=3600):
    def loop():
        time.sleep(60)            # let the server start first
        while True:
            try:
                if not made_today(app):
                    make_backup(app)
            except Exception:     # pragma: no cover - logged, retried next hour
                app.logger.exception("daily backup failed")
            time.sleep(every_seconds)
    threading.Thread(target=loop, name="enesai-backup", daemon=True).start()
