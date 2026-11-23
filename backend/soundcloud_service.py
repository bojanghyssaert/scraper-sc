"""
SoundCloud service module.

Bevat alle logica voor het ophalen van de client_id,
track-metadata en de download-URL — zonder enige GUI-afhankelijkheid.
"""

import re
import urllib.parse
from typing import Callable
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10

_cached_client_id: str | None = None
_on_client_id_reset_callbacks: list[Callable[[], None]] = []
_on_client_id_updated_callbacks: list[Callable[[str], None]] = []


class SoundCloudError(Exception):
    """Domein-specifieke fout voor SoundCloud-bewerkingen."""


class SoundCloudDRMError(SoundCloudError):
    """Domein-specifieke fout voor DRM-beveiligde SoundCloud tracks."""


def register_reset_callback(cb: Callable[[], None]) -> None:
    """Registreert een callback die wordt aangeroepen wanneer de client_id wordt gereset."""
    if cb not in _on_client_id_reset_callbacks:
        _on_client_id_reset_callbacks.append(cb)


def register_update_callback(cb: Callable[[str], None]) -> None:
    """Registreert een callback die wordt aangeroepen wanneer een nieuwe client_id is ingesteld."""
    if cb not in _on_client_id_updated_callbacks:
        _on_client_id_updated_callbacks.append(cb)


def reset_client_id() -> None:
    """
    Maakt de gecachete client_id ongeldig zodat bij een volgend verzoek
    een nieuwe client_id wordt opgehaald.
    """
    global _cached_client_id
    _cached_client_id = None
    for cb in list(_on_client_id_reset_callbacks):
        try:
            cb()
        except Exception:
            pass


def _set_cached_client_id(cid: str | None) -> None:
    """Stelt de gecachete client_id in en verwittigt geregistreerde callbacks."""
    global _cached_client_id
    _cached_client_id = cid
    if cid is not None:
        for cb in list(_on_client_id_updated_callbacks):
            try:
                cb(cid)
            except Exception:
                pass


def get_cached_client_id() -> str:
    """
    Haalt de gecachete client_id op of vraagt een nieuwe op als deze nog niet gecached is.

    Returns:
        De 32-tekens client_id string.

    Raises:
        SoundCloudError: Als het ophalen van een client_id mislukt.
    """
    global _cached_client_id
    if not _cached_client_id:
        fresh_id = get_client_id()
        _set_cached_client_id(fresh_id)
    return _cached_client_id


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


def _fetch_with_retry(
    url: str,
    params: dict | None = None,
    client_id: str | None = None,
    timeout: int = TIMEOUT,
) -> tuple[requests.Response, str]:
    """
    Voert een GET-verzoek uit met een client_id.
    Als SoundCloud een HTTP 401 of 403 retourneert, wordt reset_client_id()
    aangeroepen, een verse client_id opgehaald via get_client_id(),
    en het verzoek eenmalig herhaald.

    Returns:
        tuple[requests.Response, str]: (respons, gebruikte_client_id)
    """
    active_client_id = client_id or get_cached_client_id()
    req_params = dict(params or {}) if params is not None else None

    # Bouw req_url en req_params op
    if "client_id=" in url:
        req_url = re.sub(r"([?&]client_id=)[^&]+", rf"\g<1>{active_client_id}", url)
    elif req_params is not None:
        req_url = url
        req_params["client_id"] = active_client_id
    else:
        req_url = url
        req_params = {"client_id": active_client_id}

    try:
        resp = requests.get(req_url, params=req_params, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise SoundCloudError(f"Netwerkfout bij SoundCloud-verzoek: {exc}") from exc

    # Bij 401 of 403: maak cache ongeldig, haal verse client_id op en herhaal één keer
    if resp.status_code in (401, 403):
        reset_client_id()
        active_client_id = get_client_id()
        _set_cached_client_id(active_client_id)

        if "client_id=" in url:
            req_url = re.sub(r"([?&]client_id=)[^&]+", rf"\g<1>{active_client_id}", url)
        else:
            req_params["client_id"] = active_client_id

        try:
            resp = requests.get(req_url, params=req_params, headers=HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            raise SoundCloudError(f"Netwerkfout na vernieuwen client_id: {exc}") from exc

    return resp, active_client_id


def get_track_info(track_url: str, client_id: str | None = None) -> dict:
    """
    Haalt track-metadata op via de SoundCloud /resolve API.
    Ververst automatisch de client_id als SoundCloud een HTTP 401 of 403 teruggeeft.

    Returns:
        Dict met: title, artist, artwork_url, duration_ms, filename, stream_url, etc.

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten.
    """
    active_client_id = client_id or get_cached_client_id()
    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={track_url}&client_id={active_client_id}"

    resp, active_client_id = _fetch_with_retry(resolve_url, client_id=active_client_id)

    if resp.status_code in (401, 403):
        raise SoundCloudError(
            f"SoundCloud API autorisatiefout ({resp.status_code}): client_id ongeldig of verlopen."
        )
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
    track_id = data.get("id")

    # 1. Controleer op officiële artist-downloads
    downloadable = bool(data.get("downloadable"))
    has_downloads_left = bool(data.get("has_downloads_left"))

    direct_url = None
    if downloadable and has_downloads_left and track_id:
        dl_api_url = (
            f"https://api-v2.soundcloud.com/tracks/{track_id}/download"
            f"?client_id={active_client_id}"
        )
        try:
            dl_resp, active_client_id = _fetch_with_retry(dl_api_url, client_id=active_client_id)
            if dl_resp.status_code == 200:
                direct_url = dl_resp.json().get("redirectUri")
        except Exception:
            direct_url = None

    transcodings = data.get("media", {}).get("transcodings", [])
    track_authorization = data.get("track_authorization")

    stream_url = None
    stream_protocol = None
    media_type = None
    extension = None

    if direct_url:
        stream_url = direct_url
        stream_protocol = "direct"

        # Bepaal extensie en MIME-type voor de officiële download
        orig_format = data.get("original_format")
        if orig_format:
            extension = f".{orig_format.lstrip('.').lower()}"
        else:
            clean_direct_url = direct_url.split("?")[0].lower()
            if clean_direct_url.endswith(".flac"):
                extension = ".flac"
            elif clean_direct_url.endswith(".wav"):
                extension = ".wav"
            elif clean_direct_url.endswith(".aif") or clean_direct_url.endswith(".aiff"):
                extension = ".aiff"
            elif clean_direct_url.endswith(".m4a"):
                extension = ".m4a"
            elif clean_direct_url.endswith(".ogg"):
                extension = ".ogg"
            else:
                extension = ".mp3"

        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".aiff": "audio/aiff",
            ".aif": "audio/aiff",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
        }
        media_type = mime_map.get(extension, "audio/mpeg")
    else:
        # Zoek naar onbeveiligde streams in volgorde van voorkeur (encrypted wordt overgeslagen):
        # 1. progressive met "mpeg" in mime_type (.mp3, audio/mpeg)
        # 2. hls met ("mpegurl" in mime_type of "mpeg" in mime_type) (.mp3, audio/mpeg)
        # 3. hls met "mp4" in mime_type (.m4a, audio/mp4)
        candidates = []

        # 1. Progressive met "mpeg" in mime_type
        for transcoding in transcodings:
            fmt = transcoding.get("format", {})
            protocol = fmt.get("protocol", "")
            mime = fmt.get("mime_type", "")
            if "encrypted" in protocol.lower():
                continue
            if protocol == "progressive" and "mpeg" in mime:
                candidates.append({
                    "stream_url": transcoding.get("url"),
                    "stream_protocol": "progressive",
                    "media_type": "audio/mpeg",
                    "extension": ".mp3",
                })
                break

        # 2. HLS met "mpegurl" of "mpeg" in mime_type
        for transcoding in transcodings:
            fmt = transcoding.get("format", {})
            protocol = fmt.get("protocol", "")
            mime = fmt.get("mime_type", "")
            if "encrypted" in protocol.lower():
                continue
            if protocol == "hls" and ("mpegurl" in mime or "mpeg" in mime):
                candidates.append({
                    "stream_url": transcoding.get("url"),
                    "stream_protocol": "hls",
                    "media_type": "audio/mpeg",
                    "extension": ".mp3",
                })
                break

        # 3. HLS met "mp4" in mime_type
        for transcoding in transcodings:
            fmt = transcoding.get("format", {})
            protocol = fmt.get("protocol", "")
            mime = fmt.get("mime_type", "")
            if "encrypted" in protocol.lower():
                continue
            if protocol == "hls" and "mp4" in mime:
                candidates.append({
                    "stream_url": transcoding.get("url"),
                    "stream_protocol": "hls",
                    "media_type": "audio/mp4",
                    "extension": ".m4a",
                })
                break

        # Valideer kandidaten in prioriteitsvolgorde; sla streams over die 404 geven bij SoundCloud
        for cand in candidates:
            try:
                params = {}
                if track_authorization:
                    params["track_authorization"] = track_authorization
                chk, active_client_id = _fetch_with_retry(
                    cand["stream_url"],
                    params=params,
                    client_id=active_client_id,
                )
                if chk.status_code == 200 and chk.json().get("url"):
                    stream_url = cand["stream_url"]
                    stream_protocol = cand["stream_protocol"]
                    media_type = cand["media_type"]
                    extension = cand["extension"]
                    break
            except Exception:
                continue

        # Fallback op eerste kandidaat als alle validatiechecks faalden (bijv. bij tijdelijke netwerkfout)
        if not stream_url and candidates:
            first = candidates[0]
            stream_url = first["stream_url"]
            stream_protocol = first["stream_protocol"]
            media_type = first["media_type"]
            extension = first["extension"]

    if not stream_url:
        # Lijst van beschikbare formaten printen naar de terminal
        format_list = [
            f"{t.get('format', {}).get('protocol')} ({t.get('format', {}).get('mime_type')})"
            for t in transcodings
        ]
        print(f"Beschikbare formaten voor '{title}':", format_list)

        # Controleer of er alleen encrypted-hls aanwezig is
        has_encrypted = any("encrypted" in t.get("format", {}).get("protocol", "").lower() for t in transcodings)
        has_unencrypted = any(
            t.get("format", {}).get("protocol") in ("progressive", "hls")
            and "encrypted" not in t.get("format", {}).get("protocol", "").lower()
            for t in transcodings
        )

        if (has_encrypted and not has_unencrypted) or (not transcodings and not downloadable):
            raise SoundCloudDRMError(
                f"Dit nummer ('{title}') is DRM-beveiligd door SoundCloud en kan niet worden gedownload."
            )
        else:
            formats_str = ", ".join(format_list) if format_list else "geen formaten gevonden"
            raise SoundCloudError(
                f"Geen ondersteunde onbeveiligde MP3- of M4A-stream gevonden voor '{title}'. Beschikbare formaten: {formats_str}."
            )

    # Veilige bestandsnaam met juiste extensie
    safe_artist = "".join(c for c in artist if c.isalnum() or c in " -_").strip()
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_artist} - {safe_title}{extension}" if safe_artist else f"{safe_title}{extension}"
    filename = filename or f"track{extension}"

    track_authorization = data.get("track_authorization")

    return {
        "title": title,
        "artist": artist,
        "artwork_url": artwork_url,
        "duration_ms": duration_ms,
        "filename": filename,
        "extension": extension,
        "media_type": media_type,
        "stream_url": stream_url,
        "stream_protocol": stream_protocol,
        "track_authorization": track_authorization,
        "direct_url": direct_url,
        "is_artist_download": bool(direct_url),
    }


def get_download_url(
    stream_url: str,
    client_id: str | None = None,
    track_authorization: str | None = None,
    is_direct: bool = False,
) -> str:
    """
    Wisselt de stream-URL in voor de directe CDN-downloadlink.
    Als stream_url al een directe download-URL is (bijv. van een officiële artist download),
    wordt deze direct geretourneerd.

    Ververst automatisch de client_id als SoundCloud een HTTP 401 of 403 teruggeeft.

    Returns:
        De CDN-URL van het audiobestand of HLS m3u8 playlist.

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten.
    """
    if is_direct or not stream_url.startswith("https://api-v2.soundcloud.com/media/"):
        return stream_url

    params = {}
    if track_authorization:
        params["track_authorization"] = track_authorization

    resp, _ = _fetch_with_retry(
        stream_url,
        params=params,
        client_id=client_id,
    )

    if resp.status_code in (401, 403):
        raise SoundCloudError(
            f"SoundCloud API autorisatiefout ({resp.status_code}) bij downloadlink: client_id ongeldig of verlopen."
        )

    if resp.status_code != 200:
        raise SoundCloudError(
            f"Fout bij ophalen downloadlink: HTTP {resp.status_code}."
        )

    try:
        download_url = resp.json().get("url")
    except ValueError as exc:
        raise SoundCloudError("Ongeldig antwoord bij downloadlink-aanvraag.") from exc

    if not download_url:
        raise SoundCloudError("Geen geldige downloadlocatie ontvangen van SoundCloud.")

    return download_url


def search_tracks(
    query: str,
    client_id: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """
    Zoekt tracks op SoundCloud via de /search/tracks API.
    Ververst automatisch de client_id als SoundCloud een HTTP 401 of 403 teruggeeft.

    Returns:
        Lijst met track dictionaries.

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten.
    """
    if not query or not query.strip():
        return []

    resp, _ = _fetch_with_retry(
        "https://api-v2.soundcloud.com/search/tracks",
        params={"q": query.strip(), "limit": str(limit)},
        client_id=client_id,
    )

    if resp.status_code in (401, 403):
        raise SoundCloudError(
            f"SoundCloud API autorisatiefout ({resp.status_code}) bij zoeken: client_id ongeldig of verlopen."
        )

    if resp.status_code != 200:
        raise SoundCloudError(f"SoundCloud zoek-API gaf foutcode {resp.status_code} terug.")

    try:
        data = resp.json()
        return data.get("collection", [])
    except ValueError as exc:
        raise SoundCloudError("Ongeldig JSON-antwoord van SoundCloud zoek-API.") from exc


# Alias voor brede compatibiliteit
search = search_tracks


def stream_audio(download_url: str):
    """
    Generator die het audiobestand in chunks van 64 KB streamt.
    Ondersteunt zowel directe progressive MP3-bestanden als HLS (.m3u8) streams.

    Yields:
        Bytes-chunks van het MP3-bestand.

    Raises:
        SoundCloudError: Bij netwerkfouten tijdens het streamen.
    """
    clean_url = download_url.split("?")[0].lower()
    is_hls = clean_url.endswith(".m3u8") or ".m3u8" in clean_url or "/hls" in clean_url

    if is_hls:
        try:
            m3u8_resp = requests.get(download_url, headers=HEADERS, timeout=TIMEOUT)
            m3u8_resp.raise_for_status()
            playlist_text = m3u8_resp.text
        except requests.RequestException as exc:
            raise SoundCloudError(f"Kan HLS playlist niet ophalen: {exc}") from exc

        lines = [line.strip() for line in playlist_text.splitlines() if line.strip()]

        # Controleer op #EXT-X-MAP:URI="..." (het MP4/M4A initialisatiesegment)
        map_match = re.search(r'#EXT-X-MAP:[^\r\n]*URI="([^"]+)"', playlist_text)
        init_url = urllib.parse.urljoin(download_url, map_match.group(1)) if map_match else None

        # Filter alle regels die niet met '#' beginnen (segment URLs)
        segment_urls = [
            urllib.parse.urljoin(download_url, line)
            for line in lines
            if not line.startswith("#")
        ]

        if not segment_urls:
            raise SoundCloudError("Geen segmenten gevonden in HLS playlist.")

        # Stream eerst het initialisatiesegment indien aanwezig (vereist voor fMP4 / M4A)
        if init_url:
            try:
                with requests.get(init_url, headers=HEADERS, stream=True, timeout=TIMEOUT) as init_resp:
                    if init_resp.status_code == 200:
                        for chunk in init_resp.iter_content(chunk_size=1024 * 64):
                            if chunk:
                                yield chunk
                    else:
                        raise SoundCloudError(
                            f"Fout bij downloaden van HLS init-segment: HTTP {init_resp.status_code}"
                        )
            except requests.RequestException as exc:
                raise SoundCloudError(f"Netwerkfout tijdens streamen van init-segment: {exc}") from exc

        # Stream elk segment achter elkaar door in chunks
        for seg_url in segment_urls:
            try:
                with requests.get(seg_url, headers=HEADERS, stream=True, timeout=TIMEOUT) as seg_resp:
                    if seg_resp.status_code == 200:
                        for chunk in seg_resp.iter_content(chunk_size=1024 * 64):
                            if chunk:
                                yield chunk
                    else:
                        raise SoundCloudError(
                            f"Fout bij downloaden van HLS segment: HTTP {seg_resp.status_code}"
                        )
            except requests.RequestException as exc:
                raise SoundCloudError(f"Netwerkfout tijdens streamen van segment: {exc}") from exc
    else:
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
