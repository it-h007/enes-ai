#!/bin/sh
# Fresh demo database + dev owner (dev only!) + dev server on :5055 (for browser checks)
pkill -f "[p]ython run.py" 2>/dev/null; sleep 0.5
export ENESAI_INSTANCE=${ENESAI_INSTANCE:-/tmp/ea-dev} PORT=5055 PYTHONPATH=.
rm -rf "$ENESAI_INSTANCE"
.venv/bin/python seed.py >/dev/null 2>&1
.venv/bin/python -c "
from enesai import create_app
app=create_app()
with app.app_context():
    from enesai.services.auth import create_owner
    create_owner('pronari','Pronari','Dev-vetem-lokal-2026')
"
nohup .venv/bin/python run.py > /tmp/server.log 2>&1 &
sleep 1.5
