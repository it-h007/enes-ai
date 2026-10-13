"""Log in as the dev owner and screenshot admin pages: python tools/shoot_admin.py WIDTHxHEIGHT[,full] /paneli-test/... """
import os, sys
from playwright.sync_api import sync_playwright
base, out = "http://127.0.0.1:5055", "/tmp/shots/admin"
os.makedirs(out, exist_ok=True)
size = sys.argv[1]; full = size.endswith(",full"); w, h = [int(x) for x in size.replace(",full", "").split("x")]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": w, "height": h}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/paneli-test/login"); pg.screenshot(path=out + "/login_%d.png" % w)
    pg.fill("#lg-u", "pronari"); pg.fill("#lg-p", "Dev-vetem-lokal-2026"); pg.click("button[type=submit]"); pg.wait_for_url("**/paneli-test/")
    for path in sys.argv[2:]:
        pg.goto(base + path, wait_until="networkidle"); pg.wait_for_timeout(250)
        name = path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-") + "_%d.png" % w
        pg.screenshot(path=os.path.join(out, name), full_page=full); print(name)
    for e in errs: print("JS:", e)
    b.close()
