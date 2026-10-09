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
(filled in below as work progresses)
