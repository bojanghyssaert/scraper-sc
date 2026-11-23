# 🎵 SoundCloud Python Scraper

Dit is een educatief project gebouwd in Python om muziek van SoundCloud te downloaden via API reverse engineering. Het script omzeilt de noodzaak voor een officiële API-sleutel door dynamisch de `client_id` uit de frontend van SoundCloud te scrapen en biedt een moderne, donkere grafische interface.

*Ontwikkeld als oefenproject voor data-extractie en netwerkanalyse (Toegepaste Informatica).*

---

## ✨ Functionaliteiten

* **🎨 Moderne Donkere Interface:** Strak vormgegeven GUI in SoundCloud-thema (`#181818` donkere achtergrond, `#FF5500` oranje accenten en Segoe UI typografie).
* **📋 Klembord Integratie:** Met één klik op de **"📋 Plakken"**-knop de SoundCloud-link direct in het invoerveld plaatsen.
* **🔍 Live Track Preview:** Toont direct na het resolven van de link de **titel en artiest** in de interface vóórdat het downloaden start.
* **📊 Live Voortgangsbalk:** Nauwkeurige `ttk.Progressbar` die de downloadvoortgang in realtime weergeeft in megabytes en percentage (`MB / MB (%)`) op basis van de `Content-Length`.
* **⚡ Streaming Downloads:** Audio wordt in chunks van 64 KB gestreamd (`iter_content`) om RAM-pieken te voorkomen, ideaal voor lange DJ-sets en podcasts.
* **🛡️ Robuuste Foutafhandeling & Thread-Safety:** Volledig asynchrone downloads in een daemon worker-thread met strikte UI-updates via `after()` en time-outs op alle netwerkverzoeken.

---

## ⚙️ Hoe het werkt (Onder de motorkap)

In plaats van standaard HTML-scraping, bootst dit script het gedrag van de SoundCloud webplayer na:
1. **Client ID Extractie:** Het script doorzoekt de dynamische JavaScript-bestanden van de homepage met RegEx om een actieve sessiesleutel (`client_id`) te vinden.
2. **Metadata Resolving:** Met behulp van de verborgen interne `/resolve` API wordt de openbare track-URL omgezet in nuttige metadata (JSON) met titel en artiest.
3. **Stream Filtering:** Het script filtert de JSON-data op het `progressive` audio-protocol (standaard MP3) om complexe HLS-streams te vermijden.
4. **Streaming Download:** De audiostroom wordt in chunks gestreamd (`iter_content`) en direct naar de schijf weggeschreven met live visualisatie van de voortgang.

---

## 🚀 Installatie en Setup

Zorg dat je **Python 3.x** op je systeem hebt geïnstalleerd.

1. **Clone deze repository:**
   ```bash
   git clone https://github.com/bojanghyssaert/scraper-sc.git
   cd soundcloud-scraper
   ```

2. **Maak een virtuele omgeving aan (aanbevolen):**
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Installeer de benodigde libraries:**
   ```bash
   pip install requests
   ```

---

## 💻 Gebruik

Start de applicatie via de command line:

```bash
python src/scraper.py
```

1. **Opstarten:** De applicatie zoekt automatisch naar een actieve sessiesleutel (`client_id`) en opent het venster.
2. **Link invoeren:** Klik op **"📋 Plakken"** om een gekopieerde SoundCloud track-URL in te voegen (of typ/plak handmatig).
3. **Downloaden:** 
   - Klik op **"Download MP3"**.
   - Kies de gewenste doelmap in de pop-up.
   - De **Track Preview** toont meteen de titel en artiest.
   - De **Voortgangsbalk** toont live de downloadstatus (in MB en %).
4. **Voltooid:** Na afronding verschijnt een bevestigingsbericht en is het MP3-bestand direct klaar voor gebruik.

---

## ⚠️ Disclaimer

Dit project is uitsluitend gemaakt voor **educatieve doeleinden** (het bestuderen van netwerkverkeer en API-structuren). Het ongeautoriseerd downloaden van auteursrechtelijk beschermd materiaal is in strijd met de Algemene Voorwaarden van SoundCloud. Gebruik deze tool alleen voor je eigen tracks of audio die onder een vrije licentie (zoals Creative Commons) valt.
