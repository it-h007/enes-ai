# ENES’AI SUPER MARKET — dyqani online (Flask)

Aplikacioni i plotë i dyqanit online të **ENES’AI SUPER MARKET** (Vlorë): faqja publike me dizajnin e aprovuar zi-ar, dyqani me kategori dhe oferta, shporta, arka me **vendndodhje të detyrueshme (GPS ose pikë në hartë)**, **kupona njëpërdorimësh**, faturë **PDF** me lidhje Google Maps + QR, dërgimi i faturës te **WhatsApp-i i marketit**, dhe **paneli i administrimit** me role e leje.

Teknologjia: Python 3 · Flask · SQLite · Jinja2 · ReportLab · Pillow · HTML/CSS/JavaScript i thjeshtë (pa npm, pa build).

> **Statusi:** shiko `IMPLEMENTATION_STATUS.md` për çfarë është gati, çfarë është testuar dhe çfarë pret vendimin e marketit.

---

## 1. Nisja e shpejtë

### Windows (një klik)
1. Instaloni **Python 3.11 ose më të ri** nga python.org (shënoni “Add Python to PATH”).
2. **Shpaketoni ZIP-in** (kliku i djathtë › “Extract All…”) dhe hapni dosjen `enesai-flask`. Mos e hapni `nis.bat` direkt nga brenda ZIP-it — Windows nxjerr vetëm atë skedar dhe instalimi dështon (“requirements.txt” nuk gjendet).
3. Klikoni dy herë **`nis.bat`** në dosjen e shpaketuar.
   - Herën e parë krijon mjedisin, instalon paketat dhe ju kërkon të krijoni **llogarinë e pronarit** (emri i përdoruesit + fjalëkalim i fortë, min. 12 shenja).
   - Hapet shfletuesi te `http://127.0.0.1:5000`. **Adresa e panelit është sekrete** (p.sh. `http://127.0.0.1:5000/paneli-k3x9m2q8.../login`) dhe shfaqet në dritaren e `nis.bat`. Ruajeni si faqe të preferuar; e shihni sërish me `python run.py admin-url`. `/admin` ose `/paneli` japin “faqja nuk u gjet”.
   - **Nuk ka llogari “admin” të paracaktuar.** Hyni me emrin dhe fjalëkalimin që zgjodhët vetë te pronari (fjalëkalimi nuk shfaqet ndërsa shkruani — kjo është normale).
   - **Harruat fjalëkalimin ose hyrja u bllokua?** Klikoni dy herë **`fjalekalimi.bat`** (ose `python run.py reset-password`): tregon llogaritë, vendos fjalëkalim të ri dhe heq bllokimin. Funksionon vetëm në kompjuterin ku ndodhet aplikacioni.

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
| Arka | 4 hapa | Emri, Mbiemri, Telefoni, Email (opsional) · vendndodhja **e detyrueshme** (harta hapet te Vlora; pika duhet të jetë brenda `MAX_DELIVERY_KM`, parazgjedhur 60 km nga dyqani) · cash në dorëzim (karta “së shpejti”) · kuponi + kushtet. |
| Porosia | një transaksion SQLite | Numri `EA-VVVV-NNNNN` (rritet vetë për çdo vit), kuponi shënohet “i përdorur” në mënyrë atomike, stoku ulet, të dhënat e shitësit ruhen si “fotografi” e faturës. |
| Konfirmimi + PDF | lidhje me token sekret (30 ditë) | Pa token → 404. PDF me ReportLab, lidhje e klikueshme dhe QR për Google Maps. |
| WhatsApp | `wa.me/<numri i marketit>?text=…` | Klienti shtyp “Dërgo” në WhatsApp. Kjo regjistrohet si **“hapur”**, jo si “dërguar”. Dërgimi automatik i PDF-së kërkon WhatsApp Business API (shih §5). |
| Paneli | adresë sekrete (`python run.py admin-url`) | Pronari ka çdo leje dhe nuk fshihet. Menaxherët/Operatorët marrin seksione nga matrica. **Kuponat: vetëm Pronari dhe Menaxherët.** |

### Rolet dhe lejet
Seksionet: Porositë · Faturat · Produktet · Importi CSV · Kategoritë · Abonentët · Ofertat e email-it · Kuponat · Reklamat & Njoftimet · Raportet · Regjistri · Cilësimet. Vetëm pronari: Operatorët dhe “Fshi të gjitha produktet”. Çdo veprim kontrollohet në server (403 + regjistër), jo vetëm duke fshehur butonat.

### Importi i produkteve (Excel ose CSV)
Paneli › Produktet › **Importo Excel / CSV**. Pranohet **direkt skedari i programit të marketit** (`.xlsx`, p.sh. `ARTIKUJ_TOTAL.xlsx` me kolonat **Kodi · Përshkrimi · Njësi**) ose CSV. Kolonat njihen edhe me emrat: `Çmimi`, `Kategoria`/`Grupi`, `Stoku`/`Sasia`, `Barkodi`, ose shablloni `sku, emri_sq, emri_en, kategoria, nenkategoria, marka, paketimi, njesia, barkodi, cmimi, zbritja, stoku, i_dukshem, foto_url`.
- E detyrueshme është vetëm **kodi** (dhe emri për produktet e reja). Kodi ekzistues përditësohet **vetëm me kolonat që ka skedari** — p.sh. një skedar `Kodi, Çmimi` ndryshon vetëm çmimet.
- Produktet **pa çmim ose pa kategori ruhen të fshehura** (baza nuk lejon të dukshëm pa çmim). Sapo të marrin çmim + kategori (nga një import tjetër ose nga paneli), dalin vetë në dyqan.
- Kategoritë për shumë produkte njëherësh: Produktet › filtri **“Pa kategori”** › kërkoni (p.sh. `AKULLORE`) › zgjidhni të gjitha › “Zbato për të gjitha N produktet e këtij filtri” › **Ndrysho kategorinë**.
- Kodet me hapësira (`DJATH GOUDA`) bëhen `DJATH-GOUDA` (njësoj në çdo import). Kodet 8/12/13/14 shifra ruhen edhe si barkod. `KG` → kg (“1 kg”), `COPE` → copë, `METRA` → m.
- Pa kolonë stoku: produktet e reja kanë stok 0 (“Mbaroi”), përveç nëse zgjidhni **“Stoku nuk ndiqet”** gjatë ngarkimit.
- `.xls` i vjetër nuk pranohet (ruajeni si `.xlsx`). `foto_url` nga interneti nuk shkarkohet (siguri). Asgjë nuk fshihet nga importi.

---

## Siguria (shkurt)
- **Paneli** ka adresë sekrete të rastësishme; vlerat e lehta (`admin`, `paneli`…) te `.env` injorohen.
- **Fjalëkalimet**: min. 12 shenja me shkronja dhe shifra; refuzohen të zakonshmet (“enesai”, “admin”, “123456”…). 6 gabime → bllokim 15 min.
- **Sesioni** mbyllet pas 30 min pa aktivitet dhe gjithsesi pas 12 orësh; një cookie e kopjuar në shfletues tjetër nuk pranohet.
- **Baza e të dhënave**: të gjitha pyetjet me parametra (pa SQL injection) — testohet me sulme të njohura në çdo formular; skedari nuk ka port në internet dhe nuk shërbehet kurrë. `.env`, baza, faturat dhe importet japin 404 nga interneti (të testuara).
- **Botët**: fushë-kurth e padukshme + kohë minimale te arka dhe abonimi, kufizim kërkesash; pa CAPTCHA.
- **Kopje rezervë** çdo ditë automatikisht (shih më poshtë).

## Kopjet rezervë
Kur faqja është e ndezur, krijohet **një kopje në ditë** te `instance/backups/` (ZIP: baza + fotot + faturat), ruhen 30 ditë. Kopje tani: **`backup.bat`** (ose `python run.py backup`). Kopjojini herë pas here edhe jashtë kompjuterit (USB / Google Drive); në server bëhet automatikisht (DEPLOYMENT.md §4).
**Rikthimi:** ndalni faqen → hapni ZIP-in → `enesai.sqlite3` vendoset te `instance/`, `uploads/` te `instance/uploads`, `private/invoices` te `instance/private/invoices` → nisni faqen.

## Ofertat me email
Paneli › **Ofertat e Email-it**: shkruani subjektin dhe tekstin (opsionale produktet në ofertë) → **Përgatit email-in** → për çdo grup shtypni **“Hap në Gmail”** (ose “Programi i email-it”) → email-i hapet gati, marrësit janë te **BCC** (nuk e shohin njëri-tjetrin) → **Send**.
- Marrës janë **vetëm** abonentët dhe klientët që shënuan “Dua oferta me email” te arka (pëlqimi i kërkuar me ligj).
- Grupet kanë deri në 45 marrës (kufiri i lidhjeve të email-it). Gmail i zakonshëm lejon rreth 500 marrës në ditë.
- Kush përgjigjet “STOP” hiqet te Abonentët. Më vonë, me domain-in, mund të lidhet një shërbim si Brevo (plani falas ~300 email/ditë) për dërgim automatik.

## 4. Testet
```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # 117 teste: rrugët, hyrja, lejet, ngarkimet, importi, kuponat (garë paralele), numrat e porosive, PDF, WhatsApp, etj.
```
Kontrollet në shfletues (Playwright/Chromium): `tools/e2e_checkout.py`, `tools/e2e_a11y.py`, `tools/e2e_admin.py`, `tools/shoot.py`, `tools/shoot_admin.py` (me `tools/devserver.sh`).

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
