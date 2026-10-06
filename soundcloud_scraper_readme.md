# 🎵 SoundCloud Python Scraper

Dit is een educatief project gebouwd in Python om muziek van SoundCloud te downloaden via API reverse engineering. Het script omzeilt de noodzaak voor een officiële API-sleutel door dynamisch de `client_id` uit de frontend van SoundCloud te scrapen.

*Ontwikkeld als oefenproject voor data-extractie en netwerkanalyse (Toegepaste Informatica).*

## ⚙️ Hoe het werkt (Onder de motorkap)

In plaats van standaard HTML-scraping, bootst dit script het gedrag van de SoundCloud webplayer na:
1. **Client ID Extractie:** Het script doorzoekt de dynamische JavaScript-bestanden van de homepage met RegEx om een actieve sessiesleutel (`client_id`) te vinden.
2. **Metadata Resolving:** Met behulp van de verborgen interne `/resolve` API wordt de openbare track-URL omgezet in nuttige metadata (JSON).
3. **Stream Filtering:** Het script filtert de JSON-data op het `progressive` audio-protocol (standaard MP3) om complexe HLS-streams te vermijden.
4. **Binaire Download:** De audiostroom wordt binnengehaald en direct als `.mp3` weggeschreven op de schijf.

## 🚀 Installatie en Setup

Zorg dat je **Python 3.x** op je systeem hebt geïnstalleerd.

1. **Clone deze repository:**
   ```bash
   git clone https://github.com/JOUW_GEBRUIKERSNAAM/soundcloud-scraper.git
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

## 💻 Gebruik

Start het script via de command line:

```bash
python scraper.py
```

Het script zal automatisch naar de benodigde `client_id` zoeken. Zodra deze is gevonden, zal het vragen om een SoundCloud link. Plak een geldige track-URL en de download begint vanzelf. Het `.mp3` bestand wordt opgeslagen in dezelfde map.

## ⚠️ Disclaimer

Dit project is uitsluitend gemaakt voor **educatieve doeleinden** (het bestuderen van netwerkverkeer en API-structuren). Het ongeautoriseerd downloaden van auteursrechtelijk beschermd materiaal is in strijd met de Algemene Voorwaarden van SoundCloud. Gebruik deze tool alleen voor je eigen tracks of audio die onder een vrije licentie (zoals Creative Commons) valt.