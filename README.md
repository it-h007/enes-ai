# ENES’AI SUPER MARKET — dyqani online (Flask)

Aplikacioni i plotë i dyqanit online të **ENES’AI SUPER MARKET** (Vlorë): faqja publike me dizajnin e aprovuar zi-ar, dyqani me kategori dhe oferta, shporta, arka me **vendndodhje të detyrueshme (GPS ose pikë në hartë)**, **kupona njëpërdorimësh**, faturë **PDF** me lidhje Google Maps + QR, dërgimi i faturës te **WhatsApp-i i marketit**, dhe **paneli i administrimit** me role e leje.

Teknologjia: Python 3 · Flask · SQLite · Jinja2 · ReportLab · Pillow · HTML/CSS/JavaScript i thjeshtë (pa npm, pa build).

> **Statusi:** shiko `IMPLEMENTATION_STATUS.md` për çfarë është gati, çfarë është testuar dhe çfarë pret vendimin e marketit.

---

## 1. Nisja e shpejtë

### Windows (një klik)
1. Instaloni **Python 3.11 ose më të ri** nga python.org (shënoni “Add Python to PATH”).
2. Klikoni dy herë **`nis.bat`**.
   - Herën e parë krijon mjedisin, instalon paketat dhe ju kërkon të krijoni **llogarinë e pronarit** (emri i përdoruesit + fjalëkalim i fortë, min. 12 shenja).
   - Hapet shfletuesi te `http://127.0.0.1:5000`. Paneli: `http://127.0.0.1:5000/paneli`.

### Linux / macOS
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # plotësoni SECRET_KEY për prodhim
.venv/bin/python run.py create-owner   # vetëm një herë
.venv/bin/python run.py         # http://127.0.0.1:5000
```

### Të dhëna demonstrative (opsionale, vetëm për provë)
```bash
.venv/bin/python seed.py              # 14 kategori, 9 produkte, njoftime, 3 kupona, 6 porosi — të gjitha me shenjën DEMO
.venv/bin/python seed.py --purge-demo # i fshin të gjitha të dhënat demo (të dhënat reale mbeten)
.venv/bin/python seed.py --bulk 20000 # produkte sintetike për provë shpejtësie
```
Të dhënat demo **nuk janë të dhëna të marketit** (emra, çmime, telefona të shpikur). Në panel shfaqen me etiketën **DEMO**.

---

## 2. Çfarë duhet plotësuar para publikimit
Te **Paneli › Cilësimet**:
- **Fatura & WhatsApp**: emri ligjor, NIPT, **numri i WhatsApp-it për porositë**, prefiksi i faturës, shënimi i faturës.
- **Dyqani & kontakti**: telefoni, email-i, adresa, orari; rrjetet sociale (vetëm profilet reale).
- **Vendndodhja**: koordinatat (lat/lng) ose lidhja Google Maps (ndez hartën te Kontakt).
- **Dërgesa**: tarifa dhe kufiri për dërgesë falas (vlerat 200 L / 3.000 L janë **demo**), zonat.

Fushat bosh **nuk shfaqen** në faqe në prodhim (në zhvillim shfaqen si “PLOTËSO”).

Vendime që i takojnë marketit (lista e plotë në `IMPLEMENTATION_STATUS.md`): WhatsApp manual apo automatik, teksti ligjor i `/kushtet`, rregullat e kuponave, ofruesi i hartës, alkooli (18+), teksti anglisht.

---

## 3. Si punon
| Pjesa | Ku | Shënime |
|---|---|---|
| Faqja publike | `/`, `/dyqani`, `/oferta`, `/kategorite`, `/kategoria/<slug>`, `/produkt/<id>`, `/shporta`, `/arka`, `/porosia/<nr>?t=…`, `/njoftime`, `/rreth-nesh`, `/kontakt`, `/kushtet` | Ballina është vetëm prezantim (pa “Shto në shportë”). |
| Shporta | sesioni i shfletuesit | Çmimet, stoku, kuponi dhe totali llogariten **gjithmonë në server**. |
| Arka | 4 hapa | Emri, Mbiemri, Telefoni, Email (opsional) · vendndodhja **e detyrueshme** · cash në dorëzim (karta “së shpejti”) · kuponi + kushtet. |
| Porosia | një transaksion SQLite | Numri `EA-VVVV-NNNNN` (rritet vetë për çdo vit), kuponi shënohet “i përdorur” në mënyrë atomike, stoku ulet, të dhënat e shitësit ruhen si “fotografi” e faturës. |
| Konfirmimi + PDF | lidhje me token sekret (30 ditë) | Pa token → 404. PDF me ReportLab, lidhje e klikueshme dhe QR për Google Maps. |
| WhatsApp | `wa.me/<numri i marketit>?text=…` | Klienti shtyp “Dërgo” në WhatsApp. Kjo regjistrohet si **“hapur”**, jo si “dërguar”. Dërgimi automatik i PDF-së kërkon WhatsApp Business API (shih §5). |
| Paneli | `/paneli` | Pronari ka çdo leje dhe nuk fshihet. Menaxherët/Operatorët marrin seksione nga matrica. **Kuponat: vetëm Pronari dhe Menaxherët.** |

### Rolet dhe lejet
Seksionet: Porositë · Faturat · Produktet · Importi CSV · Kategoritë · Abonentët · Ofertat e email-it · Kuponat · Reklamat & Njoftimet · Raportet · Regjistri · Cilësimet. Vetëm pronari: Operatorët dhe “Fshi të gjitha produktet”. Çdo veprim kontrollohet në server (403 + regjistër), jo vetëm duke fshehur butonat.

### Importi CSV
Kolonat: `sku, emri_sq, emri_en, kategoria, nenkategoria, marka, paketimi, cmimi, zbritja, stoku, i_dukshem, foto_url` — UTF-8 (edhe me BOM), ndarës `,` `;` ose TAB, deri 20 MB. SKU ekzistues përditësohet, i riu krijohet, asgjë nuk fshihet. Rreshtat me gabime kapërcehen dhe shkarkohen si CSV. `foto_url` nga interneti **nuk** shkarkohet (siguri); fotot ngarkohen te produkti.

---

## 4. Testet
```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # 73 teste: rrugët, hyrja, lejet, ngarkimet, importi, kuponat (garë paralele), numrat e porosive, PDF, WhatsApp, etj.
```
Kontrollet në shfletues (Playwright/Chromium): `tools/e2e_checkout.py`, `tools/shoot.py`, `tools/shoot_admin.py` (me `tools/devserver.sh`).

## 5. Integrime të çaktivizuara (dhe si aktivizohen)
| Integrimi | Gjendja | Çfarë duhet |
|---|---|---|
| Pagesa me kartë | **E çaktivizuar** (“Së shpejti”). Nuk mblidhen kurrë të dhëna karte. | Ofrues pagesash i autorizuar + integrim i veçantë. |
| WhatsApp automatik (PDF) | **E çaktivizuar** — kodi ekziston (`enesai/services/whatsapp.py`), nuk simulohet. | Llogari Meta Business e verifikuar, numër dërguesi, shabllon i aprovuar me header DOKUMENT; `WA_TOKEN`, `WA_PHONE_ID`, `WA_TEMPLATE` në `.env`; pastaj “Automatikisht” te Cilësimet. |
| Dërgimi i email-eve | **Vetëm përgatitje** (HTML + lista BCC). | Zgjedhja e një shërbimi email/SMTP dhe lidhje çabonimi për çdo marrës. |
| Shitja online e alkoolit | **E çaktivizuar** (vetëm në dyqan). | Konfirmim ligjor; `ADULT_CHECKOUT_ENABLED=true`. |
| Harta | Leaflet + pllaka OSM publike (vetëm për provë). | Ofrues pllakash me kontratë/çelës: `MAP_TILE_URL`. |

## 6. Prodhimi, kopjet rezervë, siguria
Shih **`DEPLOYMENT.md`** (HTTPS, Waitress, kopje rezervë dhe rikthim, lista e sigurisë).

## 7. Struktura
```
enesai/            aplikacioni (blueprint-et public, checkout, api, admin; services/; templates/; static/)
enesai/migrations/ skema SQLite (migrime përpara)
enesai/static/     CSS e dizajnit (pa ndryshime), fontet, imazhet, Leaflet, enesai.js, admin.js
instance/          baza e të dhënave, ngarkimet, faturat PDF private (jashtë git)
seed.py            të dhëna demo · run.py · nis.bat · tests/ · tools/
```
Krediti **NEOX WEB STUDIO** mbetet elementi i fundit i çdo faqeje publike.
