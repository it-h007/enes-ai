"""Render a list of URLs with the test client; print status codes (and the error log tail on 500)."""
import sys
from enesai import create_app
app = create_app()
c = app.test_client()
urls = sys.argv[1:]
bad = 0
for u in urls:
    r = c.get(u)
    print(r.status_code, u, len(r.data))
    safe = "".join(ch if ch.isalnum() else "_" for ch in u)[:80]
    open("/tmp/p_%s.html" % safe, "wb").write(r.data)
    bad += r.status_code >= 500
sys.exit(1 if bad else 0)
