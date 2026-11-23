---
name: quality-assurance
description: Verplichte kwaliteitsborging, architectuur- en stijlregels, automatische backend-tests (pytest, py_compile) en frontend-validatie (npm run build). Altijd gebruiken bij elke wijziging in backend/ of frontend/ vóór het aanmaken van commits en Pull Requests.
---

# 🛡️ Quality Assurance voor SoundCloud Scraper

Deze skill definieert de verplichte werkwijze en kwaliteitsstandaarden voor alle wijzigingen in de codebase (`backend/` en `frontend/`). Het doel is om elke wijziging foutloos, stabiel en zonder handmatig debugwerk op te leveren.

Geen enkele wijziging mag worden gecommit of gepusht zonder dat alle kwaliteitscontroles in deze skill succesvol zijn doorlopen.

---

## 1. Vaste Architectuur- en Stijlregels

### Backend (`backend/`)
* **Strikte scheiding van verantwoordelijkheden:**
  * **`backend/soundcloud_service.py`**: Bevat **alle** SoundCloud-interacties, scraping-, ontledings- en downloadlogica (zoals client-id resolving, metadata parsen, stream URLs ophalen, progressive vs. HLS verwerking en download streaming).
  * **`backend/main.py`**: Blijft strikt beperkt tot FastAPI routing, Pydantic request/response-validatie, dependency injection en correcte HTTP-statuscodes (bijv. 400 voor ongeldige invoer, 404 voor niet-gevonden tracks, 422 voor validatiefouten, 502/500 voor externe upstream fouten). Geen directe SoundCloud scraping- of transformatielogica in `main.py`.
* **Code-integriteit:** Schrijf schone, getypeerde Python code met duidelijke docstrings en type hints (`typing`).

### Frontend (`frontend/`)
* **Vue 3 Composition API:** Schrijf alle Vue-componenten verplicht met `<script setup>`.
* **Taal & Gebruikersinterface:** Gebruik uitsluitend duidelijke **Nederlandse labels**, placeholderteksten, knopteksten en foutmeldingen in de UI.
* **Huisstijl & Kleuren:** Handhaaf consistent het donkere thema:
  * Achtergrond basis: `#181818`
  * Kaarten / Containers / Panelen: `#242424`
  * Accentkleur (SoundCloud oranje): `#FF5500`
* **Downloadmechanisme:**
  * Gebruik voor het opslaan van gedownloade audiobestanden bij voorkeur de moderne File System Access API: `window.showSaveFilePicker()`.
  * Zorg te allen tijde voor een robuuste fallback naar een programmatisch gegenereerd `<a download>`-element (via `URL.createObjectURL(blob)`) voor browsers die de Save File Picker API niet ondersteunen of wanneer toegang wordt geweigerd.

---

## 2. Automatische Backend-tests (`pytest` + `TestClient`)

### Vereisten & Pakketbeheer
* Zorg dat `pytest` en `httpx` altijd aanwezig zijn in `requirements.txt` (vereist door FastAPI `TestClient`).
* Installeer dependencies indien nodig:
  ```bash
  pip install -r requirements.txt
  ```

### Teststructuur & Richtlijnen (`backend/tests/`)
* Onderhoud alle backend-tests in `backend/tests/` (bijv. `test_soundcloud_service.py` en `test_api.py`).
* **Geen echte internetcalls:** Alle tests moeten draaien met **gemockte SoundCloud-responses** (gebruik `unittest.mock`, `pytest-mock` of `monkeypatch`). Er mogen tijdens het testen nooit actieve verzoeken naar externe SoundCloud-servers worden gestuurd.
* **Service-dekking (`backend/soundcloud_service.py`):**
  * Ophalen en extraheren van trackmetadata (titel, artiest, artwork, duur, etc.).
  * Verwerking van `progressive` streamtranscodings.
  * Verwerking van `hls` streamtranscodings en m3u8 playlist parsing.
  * Verwerking van officiële `downloadable` tracks.
  * Correcte detectie en foutafhandeling van DRM-beveiligde of niet-beschikbare streams.
* **API Endpoint-dekking (`backend/main.py`):**
  * Gebruik `fastapi.testclient.TestClient`.
  * Test `/api/track` (succesvolle metadata/streams response, 400 bij ongeldige URL's, 404 bij niet-bestaande tracks).
  * Test `/api/download` (correcte streaming/bestandsafhandeling, headers en foutstatussen).

### Verplichte Lokale Backend-validatie
Draai vóór elke commit altijd de volgende commando's vanuit de root directory:

1. **Syntaxis- en compilatiecontrole:**
   ```bash
   python -m py_compile backend/main.py backend/soundcloud_service.py
   ```
2. **Geautomatiseerde testsuite:**
   ```bash
   pytest
   ```

Beide opdrachten moeten met exit code 0 afsluiten zonder waarschuwingen of fouten.

---

## 3. Automatische Frontend-controle

* Draai vóór elke commit waarin frontend-bestanden zijn gewijzigd (of bij gecombineerde wijzigingen) verplicht de frontend build:
  ```bash
  cd frontend
  npm run build
  ```
* **Zelfstandige probleemoplossing:**
  * Controleer de build-output nauwkeurig.
  * Los eventuele TypeScript/JavaScript fouten, ontbrekende imports, template-fouten of Vite-bundelproblemen direct zelfstandig op in de code.
  * Herhaal `npm run build` tot de build volledig schoon en zonder fouten slaagt.

---

## 4. Quality Gate: Verplichte Schakel naar `git-flow`

Deze kwaliteitscontrole fungeert als een onvoorwaardelijke poortwachter (Quality Gate) voor de `git-flow` skill:

```
[ Wijziging in backend of frontend ]
                 │
                 ▼
 ┌──────────────────────────────────────────────┐
 │ 1. python -m py_compile ...                  │ ──► Fout? ──► Direct herstellen in backend
 └──────────────────────────────────────────────┘
                 │ Geslaagd
                 ▼
 ┌──────────────────────────────────────────────┐
 │ 2. pytest (backend/tests/ met mocks)         │ ──► Fout? ──► Direct herstellen / tests updaten
 └──────────────────────────────────────────────┘
                 │ Geslaagd
                 ▼
 ┌──────────────────────────────────────────────┐
 │ 3. npm run build (in frontend/)              │ ──► Fout? ──► Direct herstellen in frontend
 └──────────────────────────────────────────────┘
                 │ Geslaagd
                 ▼
 ┌──────────────────────────────────────────────┐
 │ ✅ Quality Gate Voltooid                      │
 │ Doorgaan naar `git-flow` skill:              │
 │ - Commit aanmaken (Conventional Commits)     │
 │ - Branch pushen                              │
 │ - Pull Request openen via GitHub CLI         │
 └──────────────────────────────────────────────┘
```

**Pas wanneer `py_compile`, `pytest` én `npm run build` allemaal zonder fouten slagen, mag de `git-flow` skill worden aangeroepen om wijzigingen te committen en een Pull Request aan te maken.**
