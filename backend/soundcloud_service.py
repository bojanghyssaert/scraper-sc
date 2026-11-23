"""
SoundCloud service module.

Bevat alle logica voor het ophalen van de client_id,
track-metadata en de download-URL — zonder enige GUI-afhankelijkheid.
"""

import re
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10


class SoundCloudError(Exception):
    """Domein-specifieke fout voor SoundCloud-bewerkingen."""


def get_client_id() -> str:
    """
    Haalt dynamisch de actieve client_id op uit de SoundCloud-frontend JS.

    Returns:
        De 32-tekens client_id string.

    Raises:
        SoundCloudError: Als de client_id niet gevonden kan worden.
    """
    try:
        response = requests.get("https://soundcloud.com", headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SoundCloudError(
            f"Kan SoundCloud homepage niet bereiken: {exc}"
        ) from exc

    script_urls = re.findall(
        r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"></script>',
        response.text,
    )
    if not script_urls:
        raise SoundCloudError("Geen JS-bestanden gevonden op de SoundCloud-homepage.")

    for url in script_urls:
        try:
            js_resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if js_resp.status_code == 200:
                match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js_resp.text)
                if match:
                    return match.group(1)
        except requests.RequestException:
            continue

    raise SoundCloudError(
        "Kon geen geldige client_id vinden in de SoundCloud JS-bestanden."
    )


def get_track_info(track_url: str, client_id: str) -> dict:
    """
    Haalt track-metadata op via de SoundCloud /resolve API.

    Returns:
        Dict met: title, artist, artwork_url, duration_ms, filename, stream_url

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten.
    """
    resolve_url = (
        f"https://api-v2.soundcloud.com/resolve"
        f"?url={track_url}&client_id={client_id}"
    )
    try:
        resp = requests.get(resolve_url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SoundCloudError(f"Netwerkfout bij ophalen track: {exc}") from exc

    if resp.status_code == 404:
        raise SoundCloudError("Track niet gevonden. Controleer de URL.")
    if resp.status_code != 200:
        raise SoundCloudError(
            f"SoundCloud API gaf foutcode {resp.status_code} terug."
        )

    try:
        data = resp.json()
    except ValueError as exc:
        raise SoundCloudError("Ongeldig JSON-antwoord van SoundCloud.") from exc

    title = data.get("title") or "Onbekende titel"
    artist = (
        data.get("publisher_metadata", {}).get("artist")
        or data.get("user", {}).get("username")
        or "Onbekende artiest"
    )

    # Artwork: voorkeur 500x500, fallback op wat beschikbaar is
    artwork_url = data.get("artwork_url") or ""
    if artwork_url:
        artwork_url = artwork_url.replace("-large", "-t500x500")

    duration_ms = data.get("duration", 0)

    # Veilige bestandsnaam
    safe_artist = "".join(c for c in artist if c.isalnum() or c in " -_").strip()
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_artist} - {safe_title}.mp3" if safe_artist else f"{safe_title}.mp3"
    filename = filename or "track.mp3"

    # Zoek progressive (MP3) stream URL
    stream_url = None
    for transcoding in data.get("media", {}).get("transcodings", []):
        if transcoding.get("format", {}).get("protocol") == "progressive":
            stream_url = transcoding.get("url")
            break

    if not stream_url:
        raise SoundCloudError(
            "Geen MP3-stream beschikbaar voor dit nummer (mogelijk DRM-beschermd)."
        )

    return {
        "title": title,
        "artist": artist,
        "artwork_url": artwork_url,
        "duration_ms": duration_ms,
        "filename": filename,
        "stream_url": stream_url,
    }


def get_download_url(stream_url: str, client_id: str) -> str:
    """
    Wisselt de stream-URL in voor de directe CDN-downloadlink.

    Returns:
        De CDN-URL van het MP3-bestand.

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten.
    """
    auth_url = f"{stream_url}?client_id={client_id}"
    try:
        resp = requests.get(auth_url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        download_url = resp.json().get("url")
    except requests.RequestException as exc:
        raise SoundCloudError(f"Fout bij ophalen downloadlink: {exc}") from exc
    except ValueError as exc:
        raise SoundCloudError("Ongeldig antwoord bij downloadlink-aanvraag.") from exc

    if not download_url:
        raise SoundCloudError("Geen geldige downloadlocatie ontvangen van SoundCloud.")

    return download_url


def stream_audio(download_url: str):
    """
    Generator die het audiobestand in chunks van 64 KB streamt.

    Yields:
        Bytes-chunks van het MP3-bestand.

    Raises:
        SoundCloudError: Bij netwerkfouten tijdens het streamen.
    """
    try:
        with requests.get(
            download_url, headers=HEADERS, stream=True, timeout=TIMEOUT
        ) as resp:
            if resp.status_code != 200:
                raise SoundCloudError(
                    f"Download mislukt: HTTP {resp.status_code}."
                )
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if chunk:
                    yield chunk
    except requests.RequestException as exc:
        raise SoundCloudError(f"Netwerkfout tijdens streamen: {exc}") from exc
