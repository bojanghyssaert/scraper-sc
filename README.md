# 🎵 SoundCloud Downloader — Full-stack webapp

Educatief full-stack project dat SoundCloud-tracks als MP3 downloadt via API reverse engineering. Bestaat uit een **Python FastAPI-backend** en een **Vue 3 + Vite-frontend** met een moderne, donkere SoundCloud-stijl UI.

*Ontwikkeld als oefenproject voor data-extractie, netwerkanalyse en full-stack webontwikkeling (Toegepaste Informatica).*

---

## ✨ Functionaliteiten

| Onderdeel | Functionaliteit |
|---|---|
| 🔌 **FastAPI backend** | `client_id` automatisch ophalen, track resolven, MP3-stream doorsturen |
| 🎨 **Moderne donkere UI** | SoundCloud-kleurenpalet (`#181818` / `#FF5500`), Inter-typografie, kaarten-layout |
| 📋 **Klembord-integratie** | "Plakken"-knop voor directe URL-invoer vanuit klembord |
| 🔍 **Live Track Preview** | Cover, titel, artiest en speelduur direct na URL-invoer |
| 📊 **Live voortgangsbalk** | Realtime MB- en percentage-weergave op basis van `Content-Length` |
| 💾 **Windows Verkenner dialoog** | Native `showSaveFilePicker()` opent de echte Verkenner om de doelmap te kiezen |
| 🔄 **Automatische fallback** | Standaard browser-download voor browsers zonder `showSaveFilePicker` |

---

## ⚙️ Hoe het werkt (Onder de motorkap)

1. **Client ID Extractie:** De backend doorzoekt de SoundCloud JS-bestanden met RegEx voor een actieve sessiesleutel (`client_id`).
2. **Metadata Resolving:** Via de `/resolve` API wordt een track-URL omgezet in JSON met titel, artiest, artwork en stream-URL.
3. **Stream Filtering:** Alleen het `progressive` protocol (MP3) wordt gebruikt; HLS-streams worden vermeden.
4. **Streaming via FastAPI:** De backend streamt audio-chunks via `StreamingResponse` naar de browser, inclusief `Content-Length` voor de voortgangsbalk.
5. **Frontend Streaming:** De Vue-app leest de `ReadableStream` chunk voor chunk en schrijft direct naar het gekozen bestand via de File System Access API.

---

## 🏗️ Projectstructuur

```
soundcloud-scraper/
├── backend/
│   ├── main.py                  # FastAPI applicatie met /api/track en /api/download
│   └── soundcloud_service.py    # SoundCloud logica (geen GUI-afhankelijkheid)
├── frontend/
│   ├── src/
│   │   ├── App.vue              # Hoofd Vue-component (alles in één)
│   │   ├── main.js              # Vue app entry point
│   │   └── style.css            # Globale stijlen (donker thema)
│   ├── index.html
│   └── vite.config.js
├── src/
│   └── scraper.py               # Originele Tkinter GUI-versie (standalone)
├── requirements.txt             # Python-afhankelijkheden voor de backend
└── README.md
```

---

## 🚀 Installatie en Opstarten

### Vereisten

* **Python 3.10+** (voor `str | None` type-syntax)
* **Node.js 18+** en **npm**

---

### Stap 1 — Repository klonen

```bash
git clone https://github.com/bojanghyssaert/scraper-sc.git
cd soundcloud-scraper
```

---

### Stap 2 — Python backend

#### Virtuele omgeving aanmaken en activeren

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

#### Afhankelijkheden installeren

```bash
pip install -r requirements.txt
```

#### Backend starten

```bash
# Vanuit de root van het project
uvicorn backend.main:app --reload --port 8000
```

De API is nu beschikbaar op **http://localhost:8000**. Documentatie via Swagger UI: **http://localhost:8000/docs**

---

### Stap 3 — Vue frontend

```bash
cd frontend
npm install
npm run dev
```

De frontend is nu beschikbaar op **http://localhost:5173**

> [!IMPORTANT]
> Zorg dat de **backend op poort 8000** actief is vóórdat je de frontend opent.

---

## 💻 Gebruik

1. **Klik op "📋 Plakken"** of typ een SoundCloud track-URL in het invoerveld.
2. **Klik op "Zoek track"** — de Track Preview verschijnt met cover, titel, artiest en duur.
3. **Klik op "⬇️ Download MP3"** — het Windows Verkenner-dialoog opent om de opslaglocatie te kiezen.
4. De **voortgangsbalk** toont live de downloadstatus in MB en percentage.
5. Na voltooiing verschijnt een bevestigingsbericht.

---

## 🔌 API Referentie

| Endpoint | Methode | Parameters | Response |
|---|---|---|---|
| `/api/track` | GET | `url` (string) | JSON: `title`, `artist`, `artwork_url`, `duration_ms`, `filename` |
| `/api/download` | GET | `url` (string) | MP3 stream (`audio/mpeg`) met `Content-Disposition` en `Content-Length` |

---

## ⚠️ Disclaimer

Dit project is uitsluitend gemaakt voor **educatieve doeleinden** (het bestuderen van netwerkverkeer, API-structuren en full-stack webontwikkeling). Het ongeautoriseerd downloaden van auteursrechtelijk beschermd materiaal is in strijd met de Algemene Voorwaarden van SoundCloud. Gebruik deze tool alleen voor je eigen tracks of audio die onder een vrije licentie (zoals Creative Commons) valt.
