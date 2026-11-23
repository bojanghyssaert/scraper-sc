"""
SoundCloud service module.

Bevat alle logica voor het ophalen van de client_id,
track-metadata en de download-URL — zonder enige GUI-afhankelijkheid.
"""

import concurrent.futures
import io
import os
import re
import urllib.parse
import zipfile
from typing import Callable
import requests
from mutagen.id3 import ID3, TIT2, TPE1, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

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


def get_track_info(
    track_url: str,
    client_id: str | None = None,
    format_id: str | None = None,
) -> dict:
    """
    Haalt track-metadata op via de SoundCloud /resolve API.
    Ververst automatisch de client_id als SoundCloud een HTTP 401 of 403 teruggeeft.

    Args:
        track_url: Publieke SoundCloud track-URL.
        client_id: Optionele actieve client_id (anders gecached).
        format_id: Optioneel specifiek formaat-ID (bijv. 'original', 'mp3', 'm4a').

    Returns:
        Dict met: title, artist, artwork_url, duration_ms, filename, extension,
        media_type, stream_url, formats (lijst met beschikbare opties), etc.

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten of onbekend format_id.
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

    # Ondersteuning voor SoundCloud afspeellijsten en albums
    if data.get("kind") in ("playlist", "system-playlist"):
        playlist_title = data.get("title") or "Onbekende afspeellijst"
        playlist_artist = (
            data.get("publisher_metadata", {}).get("artist")
            or data.get("user", {}).get("username")
            or "Onbekende artiest"
        )
        playlist_artwork = data.get("artwork_url") or ""
        if playlist_artwork:
            playlist_artwork = playlist_artwork.replace("-large", "-t500x500")

        raw_tracks = data.get("tracks", [])

        # Controleer op stub tracks (SoundCloud levert na 5 nummers vaak alleen { "id": ... })
        stub_ids = [t["id"] for t in raw_tracks if isinstance(t, dict) and t.get("id") and not t.get("title")]
        fetched_map = {}
        if stub_ids:
            for i in range(0, len(stub_ids), 50):
                batch_ids = stub_ids[i:i + 50]
                ids_str = ",".join(str(bid) for bid in batch_ids)
                try:
                    b_resp, active_client_id = _fetch_with_retry(
                        "https://api-v2.soundcloud.com/tracks",
                        params={"ids": ids_str},
                        client_id=active_client_id,
                    )
                    if b_resp.status_code == 200:
                        for trk in b_resp.json():
                            if isinstance(trk, dict) and trk.get("id"):
                                fetched_map[trk["id"]] = trk
                except Exception:
                    pass

        parsed_tracks = []
        for t in raw_tracks:
            if not isinstance(t, dict):
                continue
            item = t
            if not item.get("title") and item.get("id") in fetched_map:
                item = fetched_map[item["id"]]

            t_title = item.get("title") or "Onbekende titel"
            t_artist = (
                item.get("publisher_metadata", {}).get("artist")
                or item.get("user", {}).get("username")
                or playlist_artist
            )
            t_duration = item.get("duration", 0)
            t_permalink = item.get("permalink_url") or ""

            t_downloadable = bool(item.get("downloadable")) and bool(item.get("has_downloads_left", True))
            t_transcodings = item.get("media", {}).get("transcodings", [])
            has_unenc = any(
                isinstance(tc, dict)
                and tc.get("format", {}).get("protocol") in ("progressive", "hls")
                and "encrypted" not in tc.get("format", {}).get("protocol", "").lower()
                for tc in t_transcodings
            )
            t_is_drm = (not has_unenc) and (not item.get("downloadable", False))
            can_download = not t_is_drm

            parsed_tracks.append({
                "url": t_permalink,
                "title": t_title,
                "artist": t_artist,
                "duration_ms": t_duration,
                "downloadable": can_download,
                "is_drm": t_is_drm,
            })

        if not playlist_artwork and raw_tracks:
            for t in raw_tracks:
                if isinstance(t, dict) and t.get("artwork_url"):
                    playlist_artwork = t["artwork_url"].replace("-large", "-t500x500")
                    break

        return {
            "type": "playlist",
            "title": playlist_title,
            "artist": playlist_artist,
            "artwork_url": playlist_artwork,
            "tracks": parsed_tracks,
        }

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
    track_authorization = data.get("track_authorization")
    transcodings = data.get("media", {}).get("transcodings", [])

    # Verzamel alle beschikbare onbeveiligde formaten
    available_formats: list[dict] = []

    # 1. Controleer op officiële artist-downloads indien downloadable: true
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

    if direct_url:
        orig_format = data.get("original_format")
        if orig_format:
            orig_ext = f".{orig_format.lstrip('.').lower()}"
        else:
            clean_direct_url = direct_url.split("?")[0].lower()
            if clean_direct_url.endswith(".flac"):
                orig_ext = ".flac"
            elif clean_direct_url.endswith(".wav"):
                orig_ext = ".wav"
            elif clean_direct_url.endswith(".aif") or clean_direct_url.endswith(".aiff"):
                orig_ext = ".aiff"
            elif clean_direct_url.endswith(".m4a"):
                orig_ext = ".m4a"
            elif clean_direct_url.endswith(".ogg"):
                orig_ext = ".ogg"
            else:
                orig_ext = ".mp3"

        mime_map = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".aiff": "audio/aiff",
            ".aif": "audio/aiff",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
        }
        orig_media_type = mime_map.get(orig_ext, "audio/mpeg")
        ext_upper = orig_ext.lstrip('.').upper()

        available_formats.append({
            "id": "original",
            "label": f"Origineel bestand ({ext_upper})",
            "extension": orig_ext,
            "media_type": orig_media_type,
            "stream_url": direct_url,
            "stream_protocol": "direct",
            "direct_url": direct_url,
            "is_artist_download": True,
        })

    # 2. Controleer op onbeveiligde MP3-streams (progressive voorkeur, anders HLS)
    prog_mp3 = next(
        (
            t for t in transcodings
            if t.get("format", {}).get("protocol") == "progressive"
            and "mpeg" in t.get("format", {}).get("mime_type", "")
            and "encrypted" not in t.get("format", {}).get("protocol", "").lower()
        ),
        None,
    )
    hls_mp3 = next(
        (
            t for t in transcodings
            if t.get("format", {}).get("protocol") == "hls"
            and (
                "mpegurl" in t.get("format", {}).get("mime_type", "")
                or "mpeg" in t.get("format", {}).get("mime_type", "")
            )
            and "encrypted" not in t.get("format", {}).get("protocol", "").lower()
        ),
        None,
    )

    chosen_mp3 = None
    mp3_protocol = None
    for cand in ([prog_mp3] if prog_mp3 else []) + ([hls_mp3] if hls_mp3 else []):
        cand_url = cand.get("url")
        if not cand_url:
            continue
        try:
            params = {}
            if track_authorization:
                params["track_authorization"] = track_authorization
            chk, active_client_id = _fetch_with_retry(
                cand_url,
                params=params,
                client_id=active_client_id,
            )
            if chk.status_code == 200 and chk.json().get("url"):
                chosen_mp3 = cand
                mp3_protocol = cand.get("format", {}).get("protocol", "progressive")
                break
        except Exception:
            continue

    # Fallback als validatiecheck faalde maar stream wel geconfigureerd is
    if not chosen_mp3:
        if prog_mp3:
            chosen_mp3 = prog_mp3
            mp3_protocol = "progressive"
        elif hls_mp3:
            chosen_mp3 = hls_mp3
            mp3_protocol = "hls"

    if chosen_mp3:
        available_formats.append({
            "id": "mp3",
            "label": "MP3 (Standaard)",
            "extension": ".mp3",
            "media_type": "audio/mpeg",
            "stream_url": chosen_mp3.get("url"),
            "stream_protocol": mp3_protocol,
            "direct_url": None,
            "is_artist_download": False,
        })

    # 3. Controleer op onbeveiligde M4A-streams (HLS MP4/AAC)
    hls_m4a = next(
        (
            t for t in transcodings
            if t.get("format", {}).get("protocol") == "hls"
            and "mp4" in t.get("format", {}).get("mime_type", "")
            and "encrypted" not in t.get("format", {}).get("protocol", "").lower()
        ),
        None,
    )
    if hls_m4a:
        available_formats.append({
            "id": "m4a",
            "label": "M4A (Hoge kwaliteit)",
            "extension": ".m4a",
            "media_type": "audio/mp4",
            "stream_url": hls_m4a.get("url"),
            "stream_protocol": "hls",
            "direct_url": None,
            "is_artist_download": False,
        })

    # Foutafhandeling indien er geen enkel ondersteund onbeveiligd formaat beschikbaar is
    if not available_formats:
        format_list = [
            f"{t.get('format', {}).get('protocol')} ({t.get('format', {}).get('mime_type')})"
            for t in transcodings
        ]
        print(f"Beschikbare formaten voor '{title}':", format_list)

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

    # Bepaal het geselecteerde formaat op basis van format_id of kies het eerste beschikbare formaat
    selected_format = None
    if format_id:
        selected_format = next((f for f in available_formats if f["id"] == format_id), None)
        if not selected_format:
            available_ids = ", ".join(f["id"] for f in available_formats)
            raise SoundCloudError(
                f"Formaat '{format_id}' is niet beschikbaar voor deze track. Beschikbare formaten: {available_ids}."
            )
    else:
        selected_format = available_formats[0]

    stream_url = selected_format["stream_url"]
    stream_protocol = selected_format["stream_protocol"]
    media_type = selected_format["media_type"]
    extension = selected_format["extension"]
    direct_url = selected_format["direct_url"]
    is_artist_download = selected_format["is_artist_download"]

    # Veilige bestandsnaam met juiste extensie
    safe_artist = "".join(c for c in artist if c.isalnum() or c in " -_").strip()
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    filename = f"{safe_artist} - {safe_title}{extension}" if safe_artist else f"{safe_title}{extension}"
    filename = filename or f"track{extension}"

    return {
        "type": "track",
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
        "is_artist_download": is_artist_download,
        "format_id": selected_format["id"],
        "formats": [
            {
                "id": f["id"],
                "label": f["label"],
                "extension": f["extension"],
            }
            for f in available_formats
        ],
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
    limit: int = 8,
) -> list[dict]:
    """
    Zoekt tracks op SoundCloud via de /search/tracks API.
    Ververst automatisch de client_id als SoundCloud een HTTP 401 of 403 teruggeeft.

    Returns:
        Lijst met dictionaries bevattende:
        - title (str)
        - artist (str)
        - artwork_url (str)
        - duration_ms (int)
        - permalink_url (str)
        - is_drm (bool)

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
    except ValueError as exc:
        raise SoundCloudError("Ongeldig JSON-antwoord van SoundCloud zoek-API.") from exc

    results: list[dict] = []
    for item in data.get("collection", []):
        if not isinstance(item, dict):
            continue

        title = item.get("title") or "Onbekende titel"
        artist = (
            item.get("publisher_metadata", {}).get("artist")
            or item.get("user", {}).get("username")
            or "Onbekende artiest"
        )
        artwork_url = item.get("artwork_url") or ""
        if artwork_url:
            artwork_url = artwork_url.replace("-large", "-t500x500")
        duration_ms = item.get("duration", 0)
        permalink_url = item.get("permalink_url") or ""

        downloadable = bool(item.get("downloadable")) and bool(item.get("has_downloads_left", True))
        transcodings = item.get("media", {}).get("transcodings", [])
        has_unencrypted_stream = any(
            isinstance(t, dict)
            and t.get("format", {}).get("protocol") in ("progressive", "hls")
            and "encrypted" not in t.get("format", {}).get("protocol", "").lower()
            for t in transcodings
        )
        is_drm = (not has_unencrypted_stream) and (not downloadable)

        results.append({
            "title": title,
            "artist": artist,
            "artwork_url": artwork_url,
            "duration_ms": duration_ms,
            "permalink_url": permalink_url,
            "is_drm": is_drm,
        })

    return results


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

        def _fetch_segment(seg_url: str) -> bytes:
            try:
                resp = requests.get(seg_url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code != 200:
                    raise SoundCloudError(
                        f"Fout bij downloaden van HLS segment: HTTP {resp.status_code}"
                    )
                return resp.content
            except SoundCloudError:
                raise
            except requests.RequestException as exc:
                raise SoundCloudError(
                    f"Netwerkfout tijdens streamen van segment: {exc}"
                ) from exc
            except Exception as exc:
                raise SoundCloudError(
                    f"Onverwachte fout tijdens ophalen van segment: {exc}"
                ) from exc

        # Haal HLS-segmenten parallel op met max 6 workers en yield chunks exact in playlist-volgorde
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                for segment_chunk in executor.map(_fetch_segment, segment_urls):
                    if segment_chunk:
                        yield segment_chunk
        except SoundCloudError:
            raise
        except requests.RequestException as exc:
            raise SoundCloudError(
                f"Netwerkfout tijdens parallel streamen van segmenten: {exc}"
            ) from exc
        except Exception as exc:
            raise SoundCloudError(
                f"Fout tijdens parallel streamen van HLS segmenten: {exc}"
            ) from exc
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


def embed_metadata(audio_bytes: bytes, extension: str, info: dict) -> bytes:
    """
    Voegt metadata (titel, artiest en cover-art) toe aan de gedownloade audio-bytes.
    Ondersteunt ID3 tags voor .mp3 en MP4 tags voor .m4a.
    Faalt veilig en geeft bij fouten of niet-ondersteunde formaten de ongewijzigde audio-bytes terug.
    """
    if not audio_bytes:
        return audio_bytes

    ext = ("." + extension.lstrip(".")).lower() if extension else ".mp3"

    # Haal cover art op indien artwork_url aanwezig is
    artwork_data: bytes | None = None
    artwork_url = info.get("artwork_url")
    if artwork_url and isinstance(artwork_url, str) and artwork_url.strip():
        try:
            resp = requests.get(artwork_url.strip(), headers=HEADERS, timeout=4)
            if resp.status_code == 200 and resp.content:
                artwork_data = resp.content
        except Exception:
            # Faal veilig als de cover-afbeelding niet laadt
            artwork_data = None

    title = info.get("title") or ""
    artist = info.get("artist") or ""

    if ext == ".mp3":
        try:
            bio = io.BytesIO(audio_bytes)
            try:
                tags = ID3(bio)
            except ID3NoHeaderError:
                tags = ID3()
            except Exception:
                tags = ID3()

            if title:
                tags.add(TIT2(encoding=3, text=str(title)))
            if artist:
                tags.add(TPE1(encoding=3, text=str(artist)))

            if artwork_data:
                mime = "image/png" if artwork_data.startswith(b"\x89PNG") else "image/jpeg"
                tags.add(
                    APIC(
                        encoding=3,
                        mime=mime,
                        type=3,  # Cover (front)
                        desc="Cover",
                        data=artwork_data,
                    )
                )

            tags.save(bio)
            return bio.getvalue()
        except Exception:
            # Faal veilig als metadata-tagging mislukt
            return audio_bytes

    elif ext in (".m4a", ".mp4"):
        try:
            bio = io.BytesIO(audio_bytes)
            audio = MP4(fileobj=bio)
            if audio.tags is None:
                audio.add_tags()

            if title:
                audio["\xa9nam"] = [str(title)]
            if artist:
                audio["\xa9ART"] = [str(artist)]

            if artwork_data:
                img_format = (
                    MP4Cover.FORMAT_PNG
                    if artwork_data.startswith(b"\x89PNG")
                    else MP4Cover.FORMAT_JPEG
                )
                audio["covr"] = [MP4Cover(artwork_data, imageformat=img_format)]

            audio.save(bio)
            return bio.getvalue()
        except Exception:
            # Faal veilig als metadata-tagging mislukt
            return audio_bytes

    return audio_bytes


def download_tracks_as_zip(
    track_urls: list[str],
    client_id: str | None = None,
) -> bytes:
    """
    Downloadt meerdere SoundCloud-tracks, voorziet ze van ID3/MP4 metadata en bundelt
    ze in een ZIP-archief.

    Returns:
        Bytes van het gecomprimeerde ZIP-bestand.

    Raises:
        SoundCloudError: Indien er geen tracks gedownload kunnen worden.
    """
    if not track_urls:
        raise SoundCloudError("Geen tracks opgegeven om te downloaden.")

    active_client_id = client_id or get_cached_client_id()

    def _download_one(index: int, url: str) -> tuple[int, str, bytes] | None:
        try:
            info = get_track_info(url, active_client_id)
            if info.get("type") == "playlist":
                return None
            if info.get("direct_url"):
                dl_url = info["direct_url"]
            else:
                dl_url = get_download_url(
                    info["stream_url"],
                    active_client_id,
                    info.get("track_authorization"),
                    is_direct=info.get("stream_protocol") == "direct",
                )
            chunks = stream_audio(dl_url)
            raw_audio = b"".join(chunks)
            extension = info.get("extension", ".mp3")
            final_audio = embed_metadata(raw_audio, extension, info)
            filename = info.get("filename") or f"track_{index + 1}{extension}"
            return (index, filename, final_audio)
        except Exception:
            return None

    # Parallel downloaden met maximaal 4 gelijktijdige threads
    indexed_results: list[tuple[int, str, bytes]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_download_one, idx, url)
            for idx, url in enumerate(track_urls)
        ]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res is not None:
                indexed_results.append(res)

    indexed_results.sort(key=lambda x: x[0])

    if not indexed_results:
        raise SoundCloudError("Geen van de geselecteerde tracks kon worden gedownload.")

    # Schrijf alle audiobestanden naar een ZIP in het geheugen
    zip_buffer = io.BytesIO()
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _, filename, audio_bytes in indexed_results:
            name = filename
            if name in seen_names:
                seen_names[name] += 1
                base, ext = os.path.splitext(name) if "." in name else (name, ".mp3")
                name = f"{base} ({seen_names[filename]}){ext}"
            else:
                seen_names[name] = 1

            zf.writestr(name, audio_bytes)

    return zip_buffer.getvalue()

