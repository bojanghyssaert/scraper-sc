# 🎵 SoundCloud Scraper & Downloader — Full-Stack Webapp

Een modern, educatief full-stack project om SoundCloud-tracks en afspeellijsten te doorzoeken, te beluisteren en op te slaan via API reverse-engineering. Bestaat uit een robuuste **Python FastAPI-backend** en een dynamische **Vue 3 + Vite-frontend** met een strak donker SoundCloud-thema (`#181818` / `#FF5500`).

*Ontwikkeld als educatief project voor netwerkanalyse, API-engineering, multimediabewerking en full-stack webontwikkeling.*

---

## ✨ Functionaliteiten

* **🔍 Zoeken & Directe URL-invoer:** Zoek direct naar SoundCloud-tracks op artiest of titel met automatische suggesties, of voer een specifieke track- of playlist-URL in via het invoerveld of de ingebouwde **Plakken**-knop.
* **🎧 Track Preview met Ingebouwde Audiospeler:** Bekijk vooraf artwork, tracktitel, artiestnaam en speelduur, en beluister direct een audiofragment via de geïntegreerde SoundCloud-stijl audiospeler voordat je downloadt.
* **⚡ Automatische HLS/M4A naar MP3-conversie:** Automatische verwerking van onbeveiligde HLS/AAC/M4A- en progressive streams naar universeel afspeelbare MP3-bestanden met behulp van FFmpeg.
* **🎚️ Optionele Volume-Normalisatie (-14 LUFS):** Schakel met één klik volume-normalisatie in conform de EBU R128 / SoundCloud broadcast-standaard (-14 LUFS geïntegreerd, -1.0 dBTP true peak) voor een consistent volumeniveau zonder vervorming. Keuze wordt lokaal onthouden (`localStorage`).
* **🏷️ Automatische ID3-Metadata & Cover-Art Tagging:** Automatisch insluiten van ID3v2.3 tags (titel, artiest, album/playlist, jaartal) en HD cover-art direct in het gedownloade MP3-bestand (via `mutagen`).
* **📦 Playlist Batch-Download als ZIP:** Volledige ondersteuning voor afspeellijsten en sets. Selecteer afzonderlijke tracks met selectievinkjes en download ze gebundeld in een handig `.zip`-archief.
* **🛡️ Strikte DRM- & Beveiligingsdetectie:** Automatische herkenning en heldere melding bij SoundCloud Go+ / DRM-beveiligde streams (`encrypted-hls`). Beveiligd tegen SSRF en manipulatie via strikte domein- en URL-validatie.
* **💾 Native Bestandsopslag:** Ondersteunt de moderne browser `showSaveFilePicker()` API om de opslaglocatie direct via Windows Verkenner te kiezen, met een robuuste fallback voor alle browsers.

---

## 🐳 Draaien met Docker (Windows, macOS & Linux)

De eenvoudigste manier om de applicatie op **elk besturingssysteem** te starten is via Docker. Zowel de frontend als de backend draaien dan in één container.

**Vereisten:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS) of Docker Engine (Linux).

### Starten

```bash
docker compose up --build
```

De applicatie is daarna direct bereikbaar op **http://localhost:8000**.  
Logs worden automatisch weggeschreven naar de lokale `./logs/` map.

### Afsluiten

```bash
docker compose down
```

> [!TIP]
> Na de eerste build kun je `--build` weglaten voor een snellere herstart: `docker compose up`.

---

## ⚡ Snelstarten op Windows (Één-klik)

Voor Windows is er een gebruiksvriendelijk start- en stopmechanisme beschikbaar:

1. **🚀 Starten (`scraper-start.bat`):**
   Dubbelklik op `scraper-start.bat` in Windows Verkenner (of voer `.\scraper-start.ps1` uit in PowerShell). Dit controleert automatisch bezette poorten, start zowel de **FastAPI-backend** (poort 8000) als de **Vue-frontend** (poort 5173) en opent automatisch `http://localhost:5173` in je browser zodra beide gereed zijn.
2. **🛑 Normaal afsluiten:**
   Druk simpelweg op <kbd>ENTER</kbd> (of <kbd>Ctrl+C</kbd>) in het geopende terminalvenster. Het script beëindigt netjes alle achterliggende processen.
3. **🚨 Noodstop (`scraper-stop.bat`):**
   Mocht een venster geforceerd gesloten zijn, dubbelklik dan op `scraper-stop.bat` om eventuele achtergebleven processen op poort 8000 en 5173 op te sporen en te beëindigen.

---

## 🛠️ Handmatige Installatie en Opstarten

### Vereisten
* **Python 3.10+**
* **Node.js 18+** en **npm**
* **FFmpeg** (wordt automatisch meegeleverd via het `imageio-ffmpeg` Python-pakket)

### 1. Repository klonen
```bash
git clone https://github.com/bojanghyssaert/scraper-sc.git
cd soundcloud-scraper
```

### 2. Python Backend inrichten
```bash
# Virtuele omgeving aanmaken en activeren
python -m venv venv

# Windows:
.\venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate

# Afhankelijkheden installeren
pip install -r requirements.txt

# Backend starten
uvicorn backend.main:app --reload --port 8000
```
De backend is nu actief op **http://localhost:8000**. Interactieve API-documentatie (Swagger UI) is beschikbaar op **http://localhost:8000/docs**.

### 3. Vue Frontend inrichten
Open een nieuw terminalvenster:
```bash
cd frontend
npm install
npm run dev
```
De webapplicatie is nu bereikbaar via **http://localhost:5173**.

---

## 🏗️ Projectarchitectuur

```
soundcloud-scraper/
├── .agent/skills/               # AI & ontwikkelrichtlijnen (git-flow, quality-assurance)
├── backend/
│   ├── main.py                  # FastAPI applicatie, endpoints en request-validatie
│   ├── soundcloud_service.py    # Scraping, stream-parsing, FFmpeg-conversie, ID3-tagging
│   └── tests/                   # Uitgebreide geautomatiseerde tests (pytest met mocks)
│       ├── test_api.py          # API-integratietests
│       ├── test_security.py     # URL-validatie, SSRF en input sanitization
│       └── test_soundcloud_service.py # Unit tests voor service, DRM en transcodings
├── frontend/
│   ├── public/                  # Statische assets (favicon, SVG iconenset)
│   ├── src/
│   │   ├── components/
│   │   │   └── AudioPlayer.vue  # SoundCloud-stijl HTML5 preview audiospeler
│   │   ├── App.vue              # Hoofd Vue-component (zoekbalk, preview, playlist & opties)
│   │   ├── main.js              # Entrypoint van de Vue-applicatie
│   │   └── style.css            # Donkere styling en layout
│   ├── index.html
│   └── vite.config.js
├── logs/                        # Gecentraliseerde runtime- en foutlogs (in .gitignore)
├── scraper-start.bat            # Windows 1-klik opstartscript
├── scraper-start.ps1            # PowerShell orchestration voor achtergrondprocessen
├── scraper-stop.bat             # Noodstop-script voor poort 8000 & 5173
├── pytest.ini                   # Pytest configuratie
├── requirements.txt             # Python-dependencies
└── README.md
```

---

## 🔌 API Overzicht

| Methode | Endpoint | Omschrijving | Belangrijkste parameters |
|---|---|---|---|
| `GET` | `/api/search` | Doorzoekt SoundCloud op artiest of titel | `q` (zoekterm), `limit` (optioneel, standaard 8) |
| `GET` | `/api/track` | Haalt track- of playlist-metadata op | `url` (SoundCloud-URL) |
| `GET` | `/api/preview` | Streamt direct audio voor de in-browser audiospeler | `url`, `format_id` (optioneel) |
| `GET` | `/api/download` | Downloadt afzonderlijke track met ID3-tags | `url`, `format_id` (optioneel), `normalize` (bool) |
| `POST` | `/api/download-zip` | Bundelt geselecteerde playlist-tracks in een ZIP | JSON body: `playlist_title`, `track_urls`, `normalize` |

---

## ⚠️ Disclaimer

Deze software is uitsluitend ontwikkeld en bedoeld voor **persoonlijke en educatieve doeleinden** (het bestuderen van netwerkverkeer, webapplicatie-architectuur, API reverse engineering en multimedia-transcodering). 

* Deze applicatie **omzeilt geen DRM-beveiliging** of toegangsbeperkingen (SoundCloud Go+ / `encrypted-hls` streams worden strikt geweigerd en geblokkeerd).
* Gebruik deze tool uitsluitend voor het downloaden van **je eigen audiomateriaal** of audiobestanden die expliciet met toestemming van de maker of onder een vrije licentie (zoals Creative Commons of rechtenvrije downloads) ter beschikking zijn gesteld.
* Het ongeautoriseerd downloaden van auteursrechtelijk beschermd materiaal is in strijd met de gebruiksvoorwaarden van SoundCloud. De ontwikkelaars aanvaarden geen enkele aansprakelijkheid voor oneigenlijk of onrechtmatig gebruik van deze tool.
