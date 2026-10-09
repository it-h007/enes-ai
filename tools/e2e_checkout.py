"""Browser e2e: shop → add → cart → checkout (errors, coupon, map pin) → confirmation → PDF + WhatsApp link."""
import os
import sys
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5055"
out = "/tmp/shots/e2e"; os.makedirs(out, exist_ok=True)
ok = True
def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label); ok &= bool(cond)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, geolocation={"latitude": 40.45391, "longitude": 19.48307, "accuracy": 9}, permissions=["geolocation"])
    ctx.route("https://*.tile.openstreetmap.org/**", lambda r: r.abort())
    ctx.route("https://tile.openstreetmap.org/**", lambda r: r.abort())
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(base + "/dyqani")
    pg.locator('[data-ea="add"]').first.click()
    pg.wait_for_selector(".ea-toast"); pg.wait_for_timeout(700)
    check(pg.locator("[data-ea-cart]").first.inner_text().strip() == "1", "add to cart updates badge")
    pg.goto(base + "/produkt/1050")
    pg.locator('.ea-pdp__buy [data-ea="inc"]').click(); pg.locator('.ea-pdp__buy [data-ea="inc"]').click()
    pg.locator('.ea-pdp__buy [data-ea="add"]').click(); pg.wait_for_timeout(700)
    check(pg.locator("[data-ea-cart]").first.inner_text().strip() == "4", "PDP adds stepper quantity (3)")
    pg.goto(base + "/shporta"); pg.screenshot(path=out + "/cart.png", full_page=True)
    pg.locator('.ea-citem [data-ea="inc"]').first.click(); pg.wait_for_timeout(800)
    check(pg.locator("[data-ea-cart]").first.inner_text().strip() == "5", "cart quantity + updates server cart")
    pg.goto(base + "/arka")
    pg.locator('[data-ea="confirm-order"]').click()
    pg.wait_for_selector(".ea-errsum")
    n_err = pg.locator(".ea-errsum li").count()
    check(n_err == 6, "empty submit shows 6 errors (got %d)" % n_err)
    pg.screenshot(path=out + "/checkout-errors.png")
    pg.fill("#co-name", "Test"); pg.fill("#co-surname", "Klient"); pg.fill("#co-tel", "069 555 1234")
    pg.fill("#co-addr", "Rr. Testi, Pall. 1"); pg.select_option("#co-zone", "Lungomare")
    pg.fill("#cp-code", "NUKEKZISTON"); pg.keyboard.press("Enter"); pg.wait_for_timeout(600)
    check("nuk ekziston" in pg.locator(".ea-coupon__msg").inner_text(), "unknown coupon rejected, Enter does not submit")
    pg.fill("#cp-code", "klient15"); pg.click('[data-ea="coupon-apply"]'); pg.wait_for_selector(".ea-coupon.is-applied")
    check("KLIENT15" in pg.locator(".ea-cofinal").inner_text(), "coupon applied (KLIENT15)")
    pg.click('[data-ea="loc-map"]'); pg.wait_for_timeout(300); pg.click('[data-ea="loc-confirm"]')
    check(pg.locator('[data-ea-loc]').get_attribute("data-state") == "ok", "map pin confirmed")
    pg.click('[data-ea="loc-gps"]'); pg.wait_for_timeout(2500); print("  loc:", pg.locator('[data-ea-loc]').get_attribute("data-state"), pg.locator('[data-ea-loc]').get_attribute("data-src"))
    check(pg.locator('[data-ea-loc]').get_attribute("data-src") == "gps", "GPS location ok")
    pg.check("#co-terms")
    pg.screenshot(path=out + "/checkout-ready.png", full_page=True)
    pg.click('[data-ea="confirm-order"]')
    try:
        pg.wait_for_url("**/porosia/**", timeout=8000)
    except Exception:
        print("  url:", pg.url); print(pg.locator(".ea-checkout__form").inner_text()[:600]); raise
    url = pg.url
    check("/porosia/EA-" in url and "?t=" in url, "redirect to signed confirmation " + url.split("?")[0])
    pg.screenshot(path=out + "/confirmation.png")
    href = pg.locator('.ea-wablock [data-ea="wa-send"]').get_attribute("href")
    text = unquote(href.split("text=", 1)[1])

    check("query=40.4539" in text and "Kuponi KLIENT15" in text and "TOTALI:" in text, "WhatsApp text has Maps link (full, with &), coupon, total")
    check("&query" not in href and "%26query" in href, "'&' inside the Maps URL is percent-encoded")
    pdf = pg.request.get(base + pg.locator('.ea-confirm__actions [data-ea="invoice-pdf"]').get_attribute("href"))
    check(pdf.status == 200 and pdf.body()[:4] == b"%PDF", "invoice PDF downloads")
    open(out + "/invoice.pdf", "wb").write(pdf.body())
    bad = pg.request.get(url.split("?")[0])
    check(bad.status == 404, "confirmation without token → 404")
    check(pg.locator("[data-ea-cart]").first.is_hidden(), "cart emptied after order")
    for e in errs: print("JS ERROR:", e)
    check(not errs, "no JS errors")
    b.close()
sys.exit(0 if ok else 1)
