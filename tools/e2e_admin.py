"""Admin browser flow: login, order drawer status change (fetch), cancel with confirm modal, coupon create/cancel, invoice search."""
import sys
from playwright.sync_api import sync_playwright
base = "http://127.0.0.1:5055"; ok = True
def check(c, label):
    global ok
    print(("PASS " if c else "FAIL ") + label); ok &= bool(c)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/paneli-test/login"); pg.fill("#lg-u", "pronari"); pg.fill("#lg-p", "gabim"); pg.click("button[type=submit]")
    check("nuk është i saktë" in pg.content(), "wrong password shows the designed error")
    pg.fill("#lg-p", "Dev-vetem-lokal-2026"); pg.click("button[type=submit]"); pg.wait_for_url("**/paneli-test/")
    pg.goto(base + "/paneli-test/porosite")
    pg.click('tr[data-ref="EA-2026-00005"] [data-ea="order-open"]'); pg.wait_for_selector("#ea-odrawer.is-open")
    check(True, "order drawer opens via fetch")
    pg.click('#ea-odrawer button[value="prep"]'); pg.wait_for_timeout(700)
    check(pg.locator('#ea-odrawer .ea-drawer__head .ea-status').inner_text().strip() == "Në përgatitje", "status changed in place")
    pg.click('#ea-odrawer button[value="cancel"]'); pg.wait_for_selector("#ea-confirm.is-open")
    check(True, "cancel asks for confirmation (danger modal)")
    pg.click('[data-ea="confirm-yes"]'); pg.wait_for_timeout(800)
    check("anuluar" in pg.locator("#ea-odrawer").inner_text().lower(), "order cancelled")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    check(pg.locator("#ea-odrawer").count() == 0, "Esc closes the drawer")
    pg.goto(base + "/paneli-test/kuponat")
    pg.click('[data-ea="coupon-pct"][data-pct="25"]')
    check(pg.input_value("#cp-new-pct") == "25" and "750" in pg.locator("[data-ea-cpex]").inner_text(), "percentage chips + example")
    pg.fill("#cp-new-code", "provabrowser"); pg.click('[data-ea="coupon-create"]'); pg.wait_for_load_state()
    check("PROVABROWSER" in pg.locator(".ea-cform__done").inner_text(), "coupon created")
    pg.locator('tr[data-code="PROVABROWSER"] button[aria-label^="Anulo"]').click(); pg.wait_for_selector("#ea-confirm.is-open")
    pg.click('[data-ea="confirm-yes"]'); pg.wait_for_load_state()
    check("Anuluar" in pg.locator('tr[data-code="PROVABROWSER"]').inner_text(), "coupon cancelled after confirmation")
    pg.fill(".ea-topbar__search input", "Hoxha"); pg.keyboard.press("Enter"); pg.wait_for_url("**/faturat?q=Hoxha")
    check("EA-2026-00006" in pg.locator(".ea-invlist").inner_text(), "global search jumps to Faturat")
    for e in errs: print("JS ERROR:", e)
    check(not errs, "no JS errors")
    b.close()
sys.exit(0 if ok else 1)
