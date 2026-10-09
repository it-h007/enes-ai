"""Browser checks: drawers (focus trap/restore, Esc, scroll lock, inert), search keyboard nav,
announcement dismiss/restore, filters clear, admin phone menu, reduced motion, no overflow."""
import sys
from playwright.sync_api import sync_playwright
base = "http://127.0.0.1:5055"; ok = True
def check(c, label):
    global ok
    print(("PASS " if c else "FAIL ") + label); ok &= bool(c)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx = b.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/")
    check(pg.locator("[data-ea-cookie]").is_visible(), "cookie notice on first visit")
    pg.click('[data-ea="cookie-ok"]'); pg.wait_for_timeout(400); pg.reload()
    check(pg.locator("[data-ea-cookie]").count() == 0, "cookie choice remembered")
    menu = pg.locator(".ea-header__menu")
    menu.click(); pg.wait_for_timeout(500)
    check(pg.locator("#ea-mnav").get_attribute("aria-hidden") == "false", "mobile menu opens")
    check(pg.evaluate("document.activeElement.closest('#ea-mnav') !== null"), "focus moved into the drawer")
    check(pg.evaluate("document.documentElement.style.overflow") == "hidden", "body scroll locked")
    check(pg.evaluate("document.querySelector('main').closest('[inert]') !== null || document.querySelector('main').hasAttribute('inert')"), "background inert")
    for _ in range(40):
        pg.keyboard.press("Tab")
    check(pg.evaluate("document.activeElement.closest('#ea-mnav') !== null"), "Tab is trapped in the drawer")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    check(pg.locator("#ea-mnav").get_attribute("aria-hidden") == "true", "Esc closes the drawer")
    check(pg.evaluate("document.activeElement.classList.contains('ea-header__menu')"), "focus restored to the menu button")
    check(pg.evaluate("document.documentElement.style.overflow") == "", "scroll unlocked")
    pg.screenshot(path="/tmp/shots/m/menu_closed.png")
    # announcements dismiss + restore (X10)
    pg.set_viewport_size({"width": 1440, "height": 900}); pg.goto(base + "/")
    for _ in range(4):
        pg.locator('.ea-acard:not([hidden]) [data-ea="dismiss"]').first.click(); pg.wait_for_timeout(80)
    pg.wait_for_selector('[data-ea="ann-restore"]')
    pg.reload()
    check(pg.locator('[data-ea="ann-restore"]').count() == 1, "dismissal remembered after reload")
    pg.click('[data-ea="ann-restore"]')
    check(pg.locator('.ea-acard:not([hidden])').count() == 4, "“Shfaqi përsëri” restores the cards")
    # search suggestions with keyboard (X3)
    pg.fill("#q", "dom"); pg.wait_for_selector(".ea-search.is-open .ea-suggest__item")
    pg.keyboard.press("ArrowDown")
    check(pg.locator('.ea-suggest [aria-selected="true"]').count() == 1, "↓ selects a suggestion")
    pg.keyboard.press("Enter"); pg.wait_for_url("**/produkt/**")
    check("/produkt/1043" in pg.url, "Enter opens the selected product")
    # filters: clear all (X11)
    pg.goto(base + "/dyqani?oferta=1&cmimi_min=100")
    pg.click("text=Pastro të gjitha"); pg.wait_for_load_state()
    check(pg.url.rstrip("/").endswith("/dyqani"), "“Pastro të gjitha” clears the filters")
    pg.goto(base + "/dyqani?oferta=1"); pg.click(".ea-shop .ea-filters >> text=Pastro filtrat")
    check(pg.url.rstrip("/").endswith("/dyqani"), "“Pastro filtrat” clears the filters")
    pg.goto(base + "/dyqani"); pg.check('.ea-shop .ea-filters input[name="kategoria"][value="bulmet"]'); pg.click('.ea-shop .ea-filters button[type=submit]')
    check("kategoria=bulmet" in pg.url and pg.locator(".ea-pcard").count() == 2, "category filter applies (2 dairy products)")
    pg.select_option('select[data-ea="sort"]', "cmimi-desc"); pg.wait_for_url("**rendit=cmimi-desc**", timeout=5000)
    check("rendit=cmimi-desc" in pg.url, "sort select navigates")
    # filter drawer on phone
    pg.set_viewport_size({"width": 390, "height": 844}); pg.goto(base + "/dyqani")
    pg.click(".ea-filterbtn"); pg.wait_for_timeout(400)
    check(pg.locator("#ea-fdrawer").get_attribute("aria-hidden") == "false", "filter drawer opens")
    pg.screenshot(path="/tmp/shots/m/filter_drawer.png")
    pg.keyboard.press("Escape")
    # no horizontal overflow at 320/390/768
    for w in (320, 390, 768, 1024, 1366):
        pg.set_viewport_size({"width": w, "height": 800})
        for path in ("/", "/dyqani", "/produkt/1050", "/shporta", "/kushtet", "/kontakt"):
            pg.goto(base + path)
            ov = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            if ov > 0:
                check(False, "no horizontal overflow %s @%d (+%dpx)" % (path, w, ov))
    check(True, "overflow sweep done (320–1366)")
    # admin phone menu (X1)
    pg.set_viewport_size({"width": 390, "height": 844})
    pg.goto(base + "/paneli/login"); pg.fill("#lg-u", "pronari"); pg.fill("#lg-p", "Dev-vetem-lokal-2026"); pg.click("button[type=submit]")
    pg.wait_for_url("**/paneli/")
    pg.click(".ea-topbar__menu"); pg.wait_for_timeout(400)
    check(pg.locator("#ea-amenu").get_attribute("aria-hidden") == "false", "admin phone menu opens")
    pg.screenshot(path="/tmp/shots/m/admin_menu.png")
    pg.click('#ea-amenu a:has-text("Faturat")'); pg.wait_for_url("**/faturat")
    check(True, "admin phone menu navigates")
    for e in errs: print("JS ERROR:", e)
    check(not errs, "no JS errors")
    b.close()
sys.exit(0 if ok else 1)
