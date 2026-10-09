"""Screenshot pages of a running server with Playwright (Chromium).
python tools/shoot.py http://127.0.0.1:5055 outdir WIDTHxHEIGHT[,full] /path ..."""
import sys
from playwright.sync_api import sync_playwright

base, out, size = sys.argv[1], sys.argv[2], sys.argv[3]
full = size.endswith(",full")
w, h = [int(x) for x in size.replace(",full", "").split("x")]
import os
os.makedirs(out, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
    ctx.add_cookies([{"name": "ea_cookie_ok", "value": "1", "url": base}])
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    for path in sys.argv[4:]:
        pg.goto(base + path, wait_until="networkidle")
        pg.wait_for_timeout(300)
        name = (path.strip("/").replace("/", "_").replace("?", "_") or "home") + "_%d.png" % w
        pg.screenshot(path=os.path.join(out, name), full_page=full)
        ov = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        print(name, "overflow" if ov else "ok")
    for e in errs:
        print("JS:", e)
    b.close()
