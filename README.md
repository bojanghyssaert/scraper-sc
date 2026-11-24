# 🎵 SoundCloud Scraper & Downloader — Full-Stack Webapp

Een modern, educatief full-stack project om SoundCloud-tracks en afspeellijsten te doorzoeken, te beluisteren en op te slaan via API reverse-engineering. Bestaat uit een robuuste, modulaire **Python FastAPI-backend** en een dynamische **Vue 3 + Vite-frontend** met een strak donker SoundCloud-thema (`#181818` / `#FF5500`).

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

## 🚀 Aan de slag

Er zijn drie manieren om de applicatie te draaien, afhankelijk van je doel:

| Methode | Doelgroep | Voordelen |
|---|---|---|
| **Docker Compose** | Iedereen (Windows, macOS, Linux) | Geen installatie van Node.js of Python vereist, 1-klik cross-platform. |
| **Windows Quickstart Scripts** | Windows lokale ontwikkeling | Hot Module Replacement (HMR) voor Vue en auto-reload voor FastAPI. |
| **Handmatige Start** | Ontwikkelaars / CI-omgevingen | Volledige controle over virtualenv en npm commando's. |

---

## 🐳 Draaien met Docker (Windows, macOS & Linux)

De eenvoudigste manier om de applicatie op **elk besturingssysteem** te starten is via Docker. Zowel de frontend als de backend draaien dan in één geoptimaliseerde multi-stage container.

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

## ⚡ Snelstarten op Windows (Lokale Ontwikkeling)

Voor lokale Windows-ontwikkeling met actieve code-herlaadfuncties (Hot Reload):

1. **🚀 Starten (`scraper-start.bat`):**  
   Dubbelklik op `scraper-start.bat` in Windows Verkenner (of voer `.\scraper-start.ps1` uit in PowerShell). Dit script:
   - Controleert automatisch of `venv` en `frontend/node_modules` aanwezig zijn.
   - Ruimt eventueel achtergebleven processen op poort 8000 en 5173 op.
   - Start de **FastAPI-backend** met auto-reload (`http://localhost:8000`).
   - Start de **Vite-ontwikkelserver** met Hot Module Replacement (`http://localhost:5173`).
   - Controleert de readiness via `/api/health` en opent automatisch je browser.
2. **🛑 Normaal afsluiten:**  
   Druk op <kbd>ENTER</kbd> (of <kbd>Ctrl+C</kbd>) in het consolevenster om alle achtergrondprocessen netjes te stoppen.
3. **🚨 Noodstop (`scraper-stop.bat`):**  
   Mocht een venster geforceerd zijn gesloten, dubbelklik dan op `scraper-stop.bat` om processen op poort 8000 en 5173 direct te beëindigen.

---

## 🛠️ Handmatige Installatie en Opstarten

### Vereisten
* **Python 3.10+** (Python 3.11 aanbevolen)
* **Node.js 18+** (Node.js 20 LTS aanbevolen) en **npm**
* **FFmpeg** (automatisch beschikbaar gesteld via `imageio-ffmpeg` of systeempakket)

### 1. Repository klonen
```bash
git clone https://github.com/bojanghyssaert/scraper-sc.git
cd soundcloud-scraper
```

### 2. Python Backend inrichten
```bash
# Virtuele omgeving aanmaken en activeren
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Windows (Command Prompt):
.\venv\Scripts\activate.bat

# macOS / Linux:
source venv/bin/activate

# Afhankelijkheden installeren (voor ontwikkeling en testen)
pip install -r requirements-dev.txt

# Backend starten met auto-reload
uvicorn backend.main:app --reload --port 8000
```
De backend is nu actief op **http://localhost:8000**.  
Interactieve Swagger API-documentatie is beschikbaar op **http://localhost:8000/docs**.

### 3. Vue Frontend inrichten
Open een nieuw terminalvenster:
```bash
cd frontend
npm install
npm run dev
```
De webapplicatie is nu bereikbaar via **http://localhost:5173**.

---

## 🧪 Geautomatiseerde Tests

Het project beschikt over uitgebreide testsuites voor zowel de backend als de frontend:

### Backend Tests (Python / Pytest)

De backend suite bevat **115 geautomatiseerde tests** die alle security checks, API-routes, scraping, media-conversie en foutafhandeling met mocks valideren:

```bash
# Volledige testsuite draaien
pytest

# Met uitgebreide output
pytest backend/tests/ -v --tb=short

# Syntaxis- en compilatiecontrole
python -m py_compile backend/main.py backend/soundcloud_service.py
```

* `backend/tests/test_api.py`: Integratietests voor alle FastAPI endpoints (`/api/search`, `/api/track`, `/api/preview`, `/api/download`, `/api/download-zip`, `/api/health`).
* `backend/tests/test_security.py`: Valideert beveiliging tegen SSRF, URL-manipulatie, ongeldige SoundCloud-domeinen en path traversal.
* `backend/tests/test_soundcloud_service.py`: Unit tests voor client ID extractie, track/playlist resolutie, HLS parsing, FFmpeg transcodering, ID3 tags en DRM-detectie.

### Frontend Tests (Vitest & @vue/test-utils)

De frontend suite bevat **33 geautomatiseerde tests** verdeeld over 6 testbestanden:

```bash
cd frontend

# Eenmalige testrun
npm test

# Interactieve watch-modus tijdens ontwikkeling
npm run test:watch

# Productiebuild verifiëren
npm run build
```

* `frontend/src/__tests__/api.test.js`: Valideert API-functies, foutafhandeling en de bestandsopslag via `showSaveFilePicker` en fallback.
* `frontend/src/__tests__/composables.test.js`: Test state management in composables (`useSettings`, `useSearch`, `useTrack`, `useDownload`).
* `frontend/src/__tests__/AudioPlayer.test.js`: Test audiospeler controls, tijdformattering en audio-element integratie.
* `frontend/src/__tests__/TrackCard.test.js`: Test rendering van individuele trackkaarten, badges en downloadknoppen.
* `frontend/src/__tests__/SearchPanel.test.js`: Test zoekbalk, zoekresultatenlijst en suggesties.
* `frontend/src/__tests__/PlaylistPanel.test.js`: Test selectievinkjes, batch-selectie en zip-download triggers.

---

## 🔄 CI/CD Pipeline (GitHub Actions)

Het project maakt gebruik van GitHub Actions via `.github/workflows/ci.yml`. Bij elke **push** en **pull request** naar de `main` branch worden geautomatiseerd drie parallelle/afhankelijke jobs uitgevoerd:

1. **Backend Tests & Lint (`backend`):**
   - Draait op `ubuntu-latest` met Python 3.11 en FFmpeg.
   - Installeert afhankelijkheden via `requirements-dev.txt` met pip caching.
   - Controleert Python-compilatie (`py_compile`).
   - Voert alle 115 tests uit via `pytest`.
2. **Frontend Tests & Build (`frontend`):**
   - Draait op `ubuntu-latest` met Node.js 20.
   - Installeert dependencies met `npm ci` en npm caching.
   - Draait alle 33 component- en unit tests met `npm test`.
   - Bouwt de productie-assets via `npm run build`.
3. **Docker Build Validatie (`docker`):**
   - Bouwt de volledige multi-stage Docker image (`Dockerfile`).
   - Start een tijdelijke container en verifieert de `/api/health` endpoint.

---

## 🏗️ Projectarchitectuur

Het project volgt een strikt gescheiden, modulaire architectuur:

```
soundcloud-scraper/
├── .agent/skills/               # AI- & ontwikkelrichtlijnen (git-flow, quality-assurance)
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions CI/CD pipeline
├── backend/
│   ├── main.py                  # FastAPI applicatie, endpoints, CORS en middleware
│   ├── soundcloud_service.py    # Backwards-compatible facade voor de soundcloud package
│   ├── services/
│   │   └── soundcloud/          # Modulair SoundCloud-domeinpackage
│   │       ├── __init__.py      # Centrale export van alle service-functies en classes
│   │       ├── client.py        # HTTP client, sessiebeheer en Client ID harvesting
│   │       ├── constants.py     # Regexes, headers, format-typen en stream-constanten
│   │       ├── downloader.py    # Download-orkestratie, ZIP-bundeling en temporary files
│   │       ├── exceptions.py    # Specifieke SoundCloud exception-hiërarchie
│   │       ├── logging_config.py# Gecentraliseerde logging configuratie
│   │       ├── media.py         # FFmpeg transcodering, volume-normalisatie & ID3 tagging
│   │       ├── scraper.py       # HTML parsing, API scraping & track/playlist resolutie
│   │       └── security.py      # SSRF-preventie en domein/URL sanitization
│   └── tests/                   # Uitgebreide geautomatiseerde pytest-suites
│       ├── test_api.py          # API endpoint integratietests
│       ├── test_security.py     # Beveiligingstests (SSRF, URL injection)
│       └── test_soundcloud_service.py # Unit tests voor service en transcodings
├── frontend/
│   ├── src/
│   │   ├── __tests__/           # Vitest component- en unit tests
│   │   │   ├── api.test.js
│   │   │   ├── AudioPlayer.test.js
│   │   │   ├── composables.test.js
│   │   │   ├── PlaylistPanel.test.js
│   │   │   ├── SearchPanel.test.js
│   │   │   └── TrackCard.test.js
│   │   ├── components/          # Kleine, herbruikbare Vue 3 componenten
│   │   │   ├── AppHeader.vue    # Navigatiebalk en normalisatie-instelling
│   │   │   ├── AudioPlayer.vue  # HTML5 audio preview speler
│   │   │   ├── DrmWarning.vue   # Duidelijke DRM / Go+ waarschuwing
│   │   │   ├── PlaylistPanel.vue# Afspeellijstweergave en selectiebeheer
│   │   │   ├── SearchPanel.vue  # Zoekinvoer, suggesties en URL-plakken
│   │   │   └── TrackCard.vue    # Individuele trackkaart met formats en download
│   │   ├── composables/         # Gedeelde reactive state en businesslogica
│   │   │   ├── useDownload.js   # Single track & ZIP batch download logica
│   │   │   ├── useSearch.js     # Zoekstatus, suggesties en debounce
│   │   │   ├── useSettings.js   # Normalisatie toggle en persistentie (localStorage)
│   │   │   └── useTrack.js      # Metadata fetching en playlist selectie
│   │   ├── services/
│   │   │   └── api.js           # Gecentraliseerde API-aanroepen en bestandsopslag
│   │   ├── App.vue              # Slanke orkestratie-component (~140 regels)
│   │   ├── main.js              # Vue 3 entrypoint
│   │   └── style.css            # Donkere styling, knoppen, responsive grids
│   ├── index.html               # Single Page Application HTML shell
│   ├── package.json             # NPM dependencies & testscripts
│   └── vite.config.js           # Vite build & Vitest testconfiguratie
├── logs/                        # Gecentraliseerde runtime- en foutlogs (in .gitignore)
├── Dockerfile                   # Multi-stage productie Docker image (Node 20 + Python 3.11)
├── docker-compose.yml           # Eenvoudig opstarten van de containerized app
├── pytest.ini                   # Pytest runtime configuratie
├── requirements.txt             # Pinned productie-afhankelijkheden
├── requirements-dev.txt         # Aanvullende test- en ontwikkeltools
├── scraper-start.bat            # Windows 1-klik startscript
├── scraper-start.ps1            # Windows PowerShell orchestrator met healthcheck
├── scraper-stop.bat             # Windows noodstopscript voor actieve poorten
└── README.md                    # Projectdocumentatie
```

---

## 🔌 API Overzicht

| Methode | Endpoint | Omschrijving | Belangrijkste parameters |
|---|---|---|---|
| `GET` | `/api/health` | Healthcheck endpoint voor containers en monitoring | *Geen* |
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
