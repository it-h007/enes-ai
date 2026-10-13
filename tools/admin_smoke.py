import re, sys
from enesai import create_app
app = create_app()
with app.app_context():
    from enesai.services.auth import create_owner
    print(create_owner("pronari", "Pronari", "Sekret-i-forte-2026"))
c = app.test_client()
r = c.get("/paneli-test/login"); tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = c.post("/paneli-test/login", data={"csrf_token": tok, "username": "pronari", "password": "Sekret-i-forte-2026"})
print("login", r.status_code, r.headers.get("Location"))
bad = 0
for u in sys.argv[1:]:
    r = c.get(u)
    print(r.status_code, u, len(r.data))
    open("/tmp/a_" + re.sub(r"\W", "_", u) + ".html", "wb").write(r.data)
    bad += r.status_code >= 500
sys.exit(bad)
