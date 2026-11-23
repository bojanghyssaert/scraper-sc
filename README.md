# 🎵 SoundCloud Python Scraper

Dit is een educatief project gebouwd in Python om muziek van SoundCloud te downloaden via API reverse engineering. Het script omzeilt de noodzaak voor een officiële API-sleutel door dynamisch de `client_id` uit de frontend van SoundCloud te scrapen.

*Ontwikkeld als oefenproject voor data-extractie en netwerkanalyse (Toegepaste Informatica).*

## ⚙️ Hoe het werkt (Onder de motorkap)

In plaats van standaard HTML-scraping, bootst dit script het gedrag van de SoundCloud webplayer na:
1. **Client ID Extractie:** Het script doorzoekt de dynamische JavaScript-bestanden van de homepage met RegEx om een actieve sessiesleutel (`client_id`) te vinden.
2. **Metadata Resolving:** Met behulp van de verborgen interne `/resolve` API wordt de openbare track-URL omgezet in nuttige metadata (JSON).
3. **Stream Filtering:** Het script filtert de JSON-data op het `progressive` audio-protocol (standaard MP3) om complexe HLS-streams te vermijden.
4. **Streaming Download:** De audiostroom wordt in chunks gestreamd (`iter_content`) en direct naar de schijf weggeschreven om geheugenbelasting te voorkomen.

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

## 💻 Gebruik

Start de applicatie via de command line:

```bash
python src/scraper.py
```

1. Bij het opstarten zoekt de applicatie automatisch naar een actieve `client_id` op SoundCloud.
2. Vervolgens opent de grafische interface (Tkinter GUI):
   - Plak een geldige SoundCloud track-URL in het invoerveld.
   - Klik op de knop **"Download MP3"**.
   - Kies in het dialoogvenster de gewenste opslagmap.
3. De download wordt veilig in een achtergrondthread uitgevoerd via streaming chunks, terwijl de voortgangsstatus live in het venster zichtbaar is. Na afronding verschijnt een melding en wordt het invoerveld automatisch gewist.

## ⚠️ Disclaimer

Dit project is uitsluitend gemaakt voor **educatieve doeleinden** (het bestuderen van netwerkverkeer en API-structuren). Het ongeautoriseerd downloaden van auteursrechtelijk beschermd materiaal is in strijd met de Algemene Voorwaarden van SoundCloud. Gebruik deze tool alleen voor je eigen tracks of audio die onder een vrije licentie (zoals Creative Commons) valt.
