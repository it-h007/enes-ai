# IMPLEMENTATION_STATUS — ENES’AI SUPER MARKET (Flask)

Living document. Updated after every milestone. Status words: **DONE** (implemented and checked by an executed test or browser run), **PARTIAL**, **NOT STARTED**, **BLOCKED** (needs a client decision), **DISABLED** (built behind a switch, intentionally off).

---

## M0 — Audit (2026-10-09)

### Inputs found
| Archive | Extracted to | Contents verified |
|---|---|---|
| `ENESAI_CODEX_HANDOFF.zip` (668 entries, no unsafe paths) | `_reference/ENESAI_CODEX_HANDOFF/` (git-ignored, read-only reference) | docs (15), evidence, 64 screenshots + sample PDF, `source/authoring` (JS templates + CSS), `source/prototype/enesai-dizajni` (45 static pages + assets), `source/design-system`, `assets/pdf-fonts` (Inter Regular/Bold, Jakarta ExtraBold), 2 images sourced online |
| `ENESAI_CODEX_HANDOFF_client-originals.zip` (13 entries) | `_reference/ENESAI_CODEX_HANDOFF/assets/client-originals/` | 13 client photos (no 06 = Bukë & Pastiçeri — never received) |
| `ENESAI-dizajni-v2.zip` (extra, 313 entries) | `_reference/dizajni-v2/` | Same offline prototype v2 as `source/prototype/` (kept only for comparison) |

No imported build script was executed. `source/design-build-tools/` is not used.

### Source architecture (what the prototype really is)
- **Templates**: vanilla JS functions returning HTML strings — `00-core.js` (helpers, demo data), `10-ui.js` (`ui.*` public components), `20-pages.js` (`pages.*` + order/coupon/invoice helpers), `30-admin.js` (`admin.*`), `40-behaviour.js` (one delegated listener keyed by `data-ea`).
- **CSS**: `bundle.css` (1725 lines, container queries on `.ea-site`) + tokens. Reused **unchanged** as `static/css/enesai.css` and `static/css/tokens.css` (only the `@font-face` URLs point to `/static/fonts/`).
- **Runtime mock**: `app.js` — localStorage cart/orders/coupons/settings, jsPDF invoice, Leaflet map, simulated WhatsApp API. **Not ported**; replaced by Flask endpoints.
- No backend, DB, auth, PDF server, e-mail or WhatsApp code existed.

### Port strategy
1. Every `ui.*` / `pages.*` / `admin.*` function → Jinja macro/template with identical element order, class names, ids, `data-ea` attributes and ARIA.
2. `icon(name, cls)` → Python global from `icons.lucide-0.460.0.json` (same SVG output).
3. `40-behaviour.js` → `static/js/enesai.js` keeping the delegation model; every `hooks.*` call becomes `fetch()` to a Flask endpoint or a plain form POST (works without JS where practical).
4. Demo data → `seed.py` (flagged `is_demo=1`, visible “DEMO” marker in admin, removable with `python seed.py --purge-demo`).

### Requirements precedence applied
Latest user prompt (Codex Master Prompt V2) › CHANGELOG CR-01…CR-19 + accepted CONFLICTS entries › prototype code/screenshots › original brief.

### Decisions taken (safe, configurable defaults — none invents store facts)
| Topic | Ref | Default implemented | Changeable via |
|---|---|---|---|
| WhatsApp delivery | C-03 | **Manual `wa.me`** text to the market number. API mode exists in code but only activates with `WA_TOKEN`/`WA_PHONE_ID`/`WA_TEMPLATE` env vars; never simulated | Settings + `.env` |
| “Sent” wording | CR-11 | Customer pressing the button is stored as `wa_opened_at` (“hapur”), never as verified delivery (`wa_sent_at` only set by a confirmed API response). Confirmation copy changed minimally to say WhatsApp was *opened* | — |
| Coupon roles | C-07 | Owner + Manager (with Kuponat permission) create/cancel; operators never | Operators page |
| Coupon range / format | C-06, C-08 | 1–90 %, `^[A-Z0-9-]{4,20}$`, generator `EA-` + 6 | `COUPON_MAX_PCT` env |
| Coupon stacking / threshold | C-19, C-20 | Stacks on discounted prices; free-delivery threshold after coupon | code constant (documented) |
| Order number | C-29 | `PREFIX-YYYY-NNNNN`, **per-year counter** (restarts at 00001 each year; unique because the year is in the number) | — |
| Cancel order | DD-06 | Returns coupon to active **and restores stock** | — |
| Stock | ADMIN §10 | Decremented inside the order transaction; checkout refused if insufficient | — |
| Quantity cap | C-17 | min(stock, 20) | `MAX_QTY_PER_LINE` env |
| Delivery fee / threshold | C-15 | Demo 200 L / 3.000 L, editable in Settings, labelled demo | Settings |
| Store facts | C-16 | Empty → row hidden on public pages (production rule); never invented | Settings |
| Legal text | C-13 | `/kushtet` template text + gold “for legal review” alert kept | — |
| Fiscal status | C-12 | “FATURË POROSIE” + note that fiscal invoice is issued at payment | Settings note |
| Map tiles | C-09 | Leaflet 1.9.4 (bundled) + tile URL from `MAP_TILE_URL` (default public OSM — **not for production traffic**) | `.env` |
| Admin path | C-31 | `/paneli` default; optional obscure path via `ADMIN_PATH` env (obscurity only, never security) | `.env` |
| Login lockout | prompt | 6 failures → 15 min lock per username+IP (configurable) | `.env` |
| Favourites | C-21 | Heart toggles stored in `localStorage`; header link goes to `/dyqani?te-preferuarat=1` filtered by the stored ids (no new page designed) | — |
| Alcohol / 18+ | C-24 | Badge shown; **online ordering of adult-category products disabled** until compliance confirmed | `ADULT_CHECKOUT_ENABLED` env |
| English | C-22 | i18n layer + draft EN strings for the public UI, marked “draft — needs approval” | `enesai/i18n_en.py` |
| Newsletter | C-23 | Single opt-in, unsubscribe link per subscriber (signed token) | — |
| E-mail sending | ADMIN §12 | “Përgatit” produces the HTML + BCC list; **no SMTP sending** (DISABLED) | future |
| Card payment | V1-10 | Disabled “Së shpejti”; no card fields ever | — |
| Logos upload | Settings | PNG/JPEG/WebP only (SVG uploads refused: XSS risk) | — |

### Open client decisions (BLOCKED items) — see CONFLICTS §D
1. Market WhatsApp number; manual vs Business API (C-03).
2. Legal name, NIPT, invoice wording; legal review of `/kushtet` (C-12, C-13).
3. Real address, phones, hours, delivery fee/threshold/zones (C-15, C-16).
4. Coupon rules confirmation (C-06/07/08/19/20), yearly numbering restart (C-29).
5. Map tile provider/key (C-09).
6. Real product list, EN copy, missing/licensed photos (Bukë & Pastiçeri missing; Pije has a Shutterstock strip; Kafe & Çaj / Kafshë images from templates, licence unverified).
7. NEOX contact numbers (C-14) — shown as supplied, editable.
8. Alcohol sale rules (C-24); favourites page (C-21); laptop first screen as is (C-36).
9. Information **not in the archives**: the user prompt mentions an “original detailed 15 permissions” list and a random hidden admin URL requirement — neither text is present in `references/`. The permission set implemented is the 12 matrix sections of the design + `operators`, `dashboard`, `products_delete_all` (see M2), documented below.

### Phased plan
M1 shell + public templates → M2 schema/security/auth → M3 catalogue + admin products/categories/import → M4 cart/checkout/coupons/orders → M5 confirmation/PDF/Faturat/WhatsApp → M6 remaining admin, i18n, SEO → M7 QA, screenshots, docs, ZIP.

---

## Milestone log
| Milestone | Status | What was delivered | How it was checked |
|---|---|---|---|
| M1 — Shell + public templates | DONE | App factory, blueprints, base/partials/macros, all public pages ported 1:1 from `10-ui.js`/`20-pages.js`; `enesai.js` port of `40-behaviour.js` | Markup diff of homepage vs prototype (identical except the data-driven suggestion panel); screenshots 1440 / 1366×650 / 768 / 390 compared with `screenshots/` |
| M2 — Schema, security, auth, RBAC, audit | DONE | SQLite schema + forward migrations, append-only audit (triggers), scrypt hashes, owner bootstrap (`run.py create-owner`), server-side admin sessions + idle timeout, lockout 6→15 min, CSRF, CSP/HSTS/headers, rate limits | pytest (auth, lockout, 403 + audit, CSRF, headers) |
| M3 — Catalogue + admin products/categories/import | DONE | Shop filters/paging/FTS search, PDP, categories; admin product CRUD, images (Pillow re-encode), bulk actions, delete-all (owner, typed confirmation), categories CRUD/order, CSV import with preview/progress/error CSV | pytest + `tools/e2e_admin.py` |
| M4 — Cart, checkout, coupons, orders | DONE | Session cart with server-side totals, 4-step checkout, required GPS/map location, atomic coupon redemption, per-year order numbers, stock decrement, idempotency | pytest (incl. 8-thread coupon race, 12-thread numbering) + `tools/e2e_checkout.py` |
| M5 — Confirmation, PDF, Faturat, WhatsApp | DONE | Signed confirmation link, ReportLab PDF (clickable Maps link + QR, seller snapshot), Faturat search, manual `wa.me` to the market number, courier text; WhatsApp Business API sender (DISABLED unless credentials) | pytest (pypdf: URI annotation, Albanian glyphs), PDF rendered and compared with `invoice-pdf__EA-2026-00149-1.png` |
| M6 — Remaining admin, i18n, SEO | DONE | Orders, invoices, coupons, subscribers, e-mail offers (prepare only), ads/announcements, reports + CSV, audit page, settings; draft EN; sitemap/robots/canonical | pytest + browser screenshots of admin screens |
| M7 — QA, docs, deliverable | DONE | README (sq), DEPLOYMENT.md, `.env.example`, `nis.bat`, pinned requirements, `pytest.ini` (collection limited to `tests/` so nothing under `_reference/` is ever imported), final ZIP | See “Tests” below |

---

## CR-01 … CR-19 (CHANGELOG) — final status

| CR | Requirement | Status | Notes / deviations |
|---|---|---|---|
| CR-01 | Laptop 1366×650 first screen | DONE | Screenshot matches `laptop-1366x650-first-screen__homepage.jpg` (CSS unchanged) |
| CR-02…06 | Client photos (hero, categories, van, offers art, storefront) | DONE | Assets copied unchanged. Bukë & Pastiçeri photo never received (uses the prototype’s image); licence of 2 online images unverified |
| CR-07 | 14 categories, data-driven | DONE | From DB; demo seed creates the 14 |
| CR-08 | Working “Shiko ofertat” | DONE | Button and whole card → `/oferta` |
| CR-09 | Emri + Mbiemri + phone + optional e-mail | DONE | Server + client validation; AL mobile and international numbers |
| CR-10 | Required GPS / map location | DONE | GPS, denied→map, pin confirm; server rejects missing/invalid coordinates. Real-device GPS NOT RUN |
| CR-11 | Invoice to the market’s WhatsApp with Maps link | DONE (manual) | `wa.me/<market>?text=…` with Maps link. **Deviation:** copy says WhatsApp was *opened*; status “Hapur”, never “Dërguar” unless the API confirms. A PDF cannot be attached via `wa.me`; the message carries the full invoice text (items, coupon, totals, Maps link) and the customer can download the PDF on the confirmation page. Automatic PDF send = DISABLED |
| CR-12 | PDF with logo + seller data from Settings | DONE | Seller data snapshotted per order |
| CR-13 | Unique number + date + time | DONE | `EA-YYYY-NNNNN`, per-year counter, seconds shown |
| CR-14 | Staff invoice search | DONE | Full number, tail digits, name/surname any order, accent-free, phone |
| CR-15 | Prominent WhatsApp button | DONE | Green panel under the number; sticky bar on phones |
| CR-16 | Terms, privacy, e-mail use, cookies | DONE | `/kushtet` template text keeps the “for legal review” alert; cookie notice only on public pages |
| CR-17 | Coupons by Owner/Manager, one-time, chosen % | DONE | 1–90 %, atomic `UPDATE … WHERE status='active'` |
| CR-18 | Coupon before “Konfirmo porosinë” | DONE | Enter applies, never submits |
| CR-19 | Coupon on invoice, WhatsApp text, admin | DONE | |

---

## Acceptance checklist results (docs/ACCEPTANCE_CHECKLIST.md)

**PASS** = verified by an executed automated test, browser run or side-by-side screenshot in this environment (Chromium only). **PARTIAL** = works but something listed is missing. **NOT RUN** = needs a device/tool not available here.

### Part A — Visual
| Item | Result | Evidence |
|---|---|---|
| V-01…V-06 Branding, palette, fonts, prices, NEOX last, no invented branding | PASS | CSS/tokens/assets reused unchanged; screenshots; PDF glyph test; credit is last element (pytest) |
| V-07…V-10 Header/footer | PASS | Screenshots 1440/1366/768/390 vs `screenshots/` |
| V-11…V-18 Homepage | PASS | Page height identical to prototype at 1440 (3033 px) and 390 (4920 px); 1366×650 first screen matches |
| V-19…V-22 Shop, product, offers, categories | PASS | Screenshots desktop + mobile |
| V-23…V-28 Cart, checkout, confirmation, invoice | PASS | Screenshots; no card fields anywhere (pytest); PDF rendered with pdftoppm and compared |
| V-29 Info pages + 404 | PASS | Screenshots |
| V-30 Cookie notice scope | PASS | pytest + browser |
| V-31 Admin sidebar incl. phone menu | PASS | Screenshots + `e2e_a11y.py` (prototype defect fixed: phone menu works) |
| V-32 Every admin screen vs screenshots | PARTIAL | Dashboard, orders + drawer, Faturat, coupons, products, import compared closely; remaining screens spot-checked only |
| V-33 Status chips word + colour | PASS | Templates |
| V-34 No horizontal scroll | PASS | Measured scrollWidth on 11 public pages × 320/375/390/430/768/1024/1366/1440/1920 — 0 overflows |
| V-35 Column counts | PASS | Same CSS container queries as prototype; screenshots |
| V-36 Motion + reduced motion | PASS | Same CSS; `prefers-reduced-motion` honoured (+ fixes CSS) |

### Part B — Functional
| Item | Result | Evidence / notes |
|---|---|---|
| F-01…F-05 Navigation, CTAs, no add-to-cart on home, mobile menu focus trap/restore, skip link | PASS | pytest + `e2e_a11y.py` |
| F-06…F-08 Search suggestions (keyboard), results, filters in URL | PASS | pytest + browser |
| F-09 Pagination 24 / load-more | PASS | |
| F-10 Hidden products/categories never shown, direct URL 404 | PASS | pytest |
| F-11…F-16 Cart | PASS | pytest + `e2e_checkout.py` (clamping, undo 5 s, confirm modal for “Pastro shportën”) |
| F-17…F-25 Checkout validation, phones, e-mail, location, server re-validation, opt-in, terms, cash only, empty-cart redirect | PASS | pytest (direct POSTs without JS) + browser; real-device GPS NOT RUN |
| F-26…F-32 Coupons | PASS | pytest incl. 8-thread race → exactly one success; operator 403 logged |
| F-33…F-36 Numbering, stored fields, signed confirmation, admin orders | PASS | pytest (12-thread numbering, wrong token → 404) |
| F-37…F-40 Invoices | PASS | pytest (pypdf), browser |
| F-41, F-42, F-44, F-45 WhatsApp manual, missing number, courier, sticky bar | PASS | pytest (URL/text) + browser; opening real WhatsApp on a phone NOT RUN |
| F-43 Automatic WhatsApp | DISABLED / NOT RUN | Code + retry path exists; needs Meta approval and credentials — never simulated |
| F-46 Products (SQ/EN, ≤6 images, discount set) | PARTIAL | Images are validated and re-encoded once (products max 1200 px); 240/480/960 **variants are not generated** |
| F-47…F-50 Bulk, delete-all, categories, CSV import | PASS | pytest + `e2e_admin.py` |
| F-51…F-58 Login/lockout, operators, dashboard, subscribers, announcements, reports, audit, settings | PASS | pytest |
| F-59…F-64 Security | PASS | pytest (CSRF, 403s, upload rejection incl. SVG, escaping, rate limits in a test mode) |
| F-65, F-66 Localization | PARTIAL | Switch + cookie work; **English strings are a draft** awaiting approval |
| F-67…F-69 SEO | PARTIAL | Titles, `lang`, meta description, canonical, sitemap, robots, real 404 done; **no `og:image`** (no PNG social card exported from the SVG) |
| F-70 WebP/AVIF + srcset | NOT DONE | Images served as uploaded/re-encoded; `width/height` + lazy loading present, no srcset variants |
| F-71, F-72 Fonts preloaded, Leaflet only on `/arka`, server-side paging | PASS | |
| F-73…F-77 Accessibility (focus, labels, errors, aria-labels, modals) | PASS (automated) | `e2e_a11y.py` 23 checks; **screen-reader test NOT RUN** |
| F-78 200 % text zoom | NOT RUN | |
| F-79…F-93 CR mapping | see CR table above | |

---

## Tests

| Suite | Result |
|---|---|
| `pytest` (`tests/`, 73 tests) | **73 passed** |
| `tools/e2e_checkout.py` (Chromium, real server) | **15 PASS, 0 FAIL** |
| `tools/e2e_a11y.py` (focus trap/restore, skip link, keyboard search, admin phone menu…) | **23 PASS, 0 FAIL** |
| `tools/e2e_admin.py` | **11 PASS, 0 FAIL** |
| Overflow scan 11 pages × 9 widths (320–1920) | **0 overflows** |
| Visual comparison with handoff screenshots | Done for the screens listed in Part A |

**NOT RUN** (not possible in this environment): Safari/iOS and Firefox; real Android/iPhone GPS; opening WhatsApp on a real phone with a long text; WhatsApp Business API live send; physical printing of the PDF; screen readers (NVDA/VoiceOver); 200 % zoom; load test with tens of thousands of products in a browser (`seed.py --bulk` exists for this).

---

## Known limitations
- Product image variants / WebP / `srcset` (F-70) not implemented; one re-encoded image per upload.
- No Open Graph image.
- Rate limiting is per process (single Waitress process is the supported layout — DEPLOYMENT.md).
- E-mail campaigns are prepared (HTML + BCC list), not sent; no SMTP integration.
- Public OSM tiles are for testing only; production needs a tile provider (`MAP_TILE_URL`).
- English is a draft.

## Disabled integrations and activation conditions
| Integration | State | Activate when |
|---|---|---|
| Card payment | Disabled (“Së shpejti”), no card fields | A licensed payment provider is contracted and integrated (hosted page; never collect card data here) |
| Automatic WhatsApp (PDF) | Disabled | Verified Meta Business account, sender number, approved DOCUMENT template; `WA_TOKEN`, `WA_PHONE_ID`, `WA_TEMPLATE` in `.env`; then “Automatikisht” in Settings |
| E-mail sending | Prepare only | E-mail provider chosen, sender domain verified, per-recipient unsubscribe |
| Online sale of 18+ products | Disabled | Legal confirmation; `ADULT_CHECKOUT_ENABLED=true` |
| Production map tiles | Test default | Provider/key; `MAP_TILE_URL`, `MAP_TILE_ATTRIBUTION` |

Unresolved client decisions: see “Open client decisions” in M0 above — none were guessed; each has a safe default and a switch.
