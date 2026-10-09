#!/bin/sh
# Fresh demo database + dev server on :5055 (for browser checks)
pkill -f "[p]ython run.py" 2>/dev/null; sleep 0.5
export ENESAI_INSTANCE=${ENESAI_INSTANCE:-/tmp/ea-dev} PORT=5055
rm -rf "$ENESAI_INSTANCE"
.venv/bin/python seed.py >/dev/null
nohup .venv/bin/python run.py > /tmp/server.log 2>&1 &
sleep 1.5
