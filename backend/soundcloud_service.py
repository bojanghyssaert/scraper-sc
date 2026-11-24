"""
SoundCloud service module.

Bevat alle logica voor het ophalen van de client_id,
track-metadata en de download-URL — zonder enige GUI-afhankelijkheid.
"""

import concurrent.futures
import io
import ipaddress
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
import zipfile
from typing import Callable
import imageio_ffmpeg
import requests
from mutagen.id3 import ID3, TIT2, TPE1, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

# Project root en gecentraliseerde logging
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG_FILE = LOGS_DIR / "error.log"

logger = logging.getLogger("soundcloud_scraper")
if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        str(ERROR_LOG_FILE),
        maxBytes=1024 * 1024,  # max 1 MB
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10

# Toegestane SoundCloud hostnamen voor SSRF-beveiliging
ALLOWED_SOUNDCLOUD_HOSTS = {
    "soundcloud.com",
    "www.soundcloud.com",
    "m.soundcloud.com",
    "on.soundcloud.com",
}

# Toegestane CDN-domeinen voor audiostream SSRF-beveiliging
ALLOWED_CDN_DOMAINS = (
    "soundcloud.com",
    "sndcdn.com",
    "soundcloud.cloud",
    "akamaized.net",
    "cloudfront.net",
)

# Gereserveerde Windows bestandsnamen ter voorkoming van path traversal / OS fouten
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Maximale limieten voor resource-bescherming
MAX_STREAM_SIZE = 250 * 1024 * 1024  # 250 MB
MAX_ZIP_TRACKS = 50
MAX_FILENAME_LENGTH = 120

# Semaphore voor gelijktijdige FFmpeg-conversies
_ffmpeg_semaphore = threading.Semaphore(2)


def validate_soundcloud_url(url: str) -> str:
    """
    Valideert of een opgegeven URL een legitieme SoundCloud-URL is via HTTPS.
    Blokkeert onveilige schema's (zoals http:// of file://), IP-adressen, localhost en vreemde domeinen (SSRF-beveiliging).

    Args:
        url: De te valideren URL string.

    Returns:
        De genormaliseerde, opgeschoonde URL string.

    Raises:
        SoundCloudError: Als de URL ongeldig, onveilig of niet van SoundCloud is.
    """
    if not url or not isinstance(url, str):
        raise SoundCloudError("Geen geldige SoundCloud-URL opgegeven.")

    trimmed = url.strip()
    if not trimmed:
        raise SoundCloudError("Geen geldige SoundCloud-URL opgegeven.")

    try:
        parsed = urllib.parse.urlparse(trimmed)
    except Exception as exc:
        raise SoundCloudError(f"Ongeldige URL-syntaxis: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise SoundCloudError(
            f"Onveilig URL-schema '{parsed.scheme}://'. Alleen beveiligde 'https://' SoundCloud-links zijn toegestaan."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname not in ALLOWED_SOUNDCLOUD_HOSTS:
        raise SoundCloudError(
            f"Ongeldig SoundCloud-domein '{hostname}'. Alleen officiële SoundCloud-links zijn toegestaan "
            f"({', '.join(sorted(ALLOWED_SOUNDCLOUD_HOSTS))})."
        )

    if not parsed.path or parsed.path.strip("/") == "":
        raise SoundCloudError("Ongeldige SoundCloud-URL: er is geen track- of playlist-pad opgegeven.")

    return trimmed


def validate_cdn_url(url: str) -> str:
    """
    Valideert of een stream- of CDN-link afkomstig is van een geautoriseerd SoundCloud CDN-domein
    (*.soundcloud.com, *.sndcdn.com, *.soundcloud.cloud, *.akamaized.net, *.cloudfront.net)
    ter voorkoming van SSRF-aanvallen via audio-streams.

    Args:
        url: De stream- of CDN-URL.

    Returns:
        De gevalideerde URL string.

    Raises:
        SoundCloudError: Als het URL-schema niet HTTPS is of het doeldomein niet geautoriseerd is.
    """
    if not url or not isinstance(url, str):
        raise SoundCloudError("Ongeldige stream- of CDN-URL.")

    trimmed = url.strip()
    try:
        parsed = urllib.parse.urlparse(trimmed)
    except Exception as exc:
        raise SoundCloudError(f"Ongeldige stream-URL-syntaxis: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise SoundCloudError(
            f"Onveilig URL-schema '{parsed.scheme}://' voor audiostream: behoort niet tot SoundCloud of het SoundCloud CDN. Alleen 'https://' is toegestaan."
        )

    if parsed.username or parsed.password:
        raise SoundCloudError("Inloggegevens in de stream-URL zijn niet toegestaan.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SoundCloudError("Geen geldig hostadres in stream-URL.")

    # Blokkeer localhost expliciet
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise SoundCloudError(
            f"Onveilige audiostream-locatie: localhost '{hostname}' behoort niet tot SoundCloud of het SoundCloud CDN."
        )

    # Blokkeer IP-adressen (zoals 127.0.0.1, 169.254.169.254, etc.)
    try:
        ipaddress.ip_address(hostname)
        raise SoundCloudError(
            f"Onveilige audiostream-locatie: IP-adres '{hostname}' behoort niet tot SoundCloud of het SoundCloud CDN."
        )
    except ValueError:
        pass

    is_valid_host = any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in ALLOWED_CDN_DOMAINS
    )
    if not is_valid_host:
        raise SoundCloudError(
            f"Onveilige audiostream-locatie: domein '{hostname}' behoort niet tot SoundCloud of het SoundCloud CDN."
        )

    return trimmed


def sanitize_filename(name: str, extension: str = "") -> str:
    """
    Schoont een bestandsnaam grondig op tegen Path Traversal en ongeldige Windows-tekens.

    - Verwijdert padscheidingstekens (/, \\, ..) en stuurtekens.
    - Vervangt ongeldige Windows-tekens (<>:"/\\|?*).
    - Voorkomt gereserveerde Windows-namen (CON, PRN, AUX, NUL, COM1-9, LPT1-9).
    - Begrenst de bestandsnaam op maximaal 120 tekens (exclusief extensie).
    - Zorgt voor een geldige extensie en veilige fallback als de naam leeg zou raken.

    Args:
        name: De gewenste basisbestandsnaam of volledige bestandsnaam.
        extension: Optionele extensie (bijv. '.mp3', '.zip').

    Returns:
        Veilige bestandsnaam met extensie.
    """
    if not name or not isinstance(name, str):
        raw_name = "track"
    else:
        raw_name = name.strip()

    # Normaliseer extensie
    clean_ext = ""
    if extension:
        clean_ext = ("." + extension.lstrip(".")).lower()

    # Als de naam al eindigt op de extensie, strip die van de basisnaam
    if clean_ext and raw_name.lower().endswith(clean_ext):
        raw_name = raw_name[:-len(clean_ext)]
    elif "." in raw_name and not clean_ext:
        parts = raw_name.rsplit(".", 1)
        raw_name, clean_ext = parts[0], f".{parts[1].lower()}"

    # Verwijder directory traversal patronen (..)
    while ".." in raw_name:
        raw_name = raw_name.replace("..", "")

    # Vervang ongeldige Windows tekens en padscheidingstekens door een underscore
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', '_', raw_name)

    # Vervang meervoudige spaties of underscores door een enkele spatie
    sanitized = re.sub(r'[\s_]+', ' ', sanitized).strip(" ._")

    # Begrens op maximaal 120 tekens (exclusief extensie)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        sanitized = sanitized[:MAX_FILENAME_LENGTH].rstrip(" ._")

    # Controleer op lege naam of gereserveerde Windows bestandsnamen
    if not sanitized:
        sanitized = "track"
    elif sanitized.upper() in WINDOWS_RESERVED_NAMES:
        sanitized = f"track_{sanitized}"

    return f"{sanitized}{clean_ext}"


_cached_client_id: str | None = None
_on_client_id_reset_callbacks: list[Callable[[], None]] = []
_on_client_id_updated_callbacks: list[Callable[[str], None]] = []


class SoundCloudError(Exception):
    """Domein-specifieke fout voor SoundCloud-bewerkingen."""

    def __init__(self, message: str = "", *args):
        super().__init__(message, *args)
        import sys
        has_exc = sys.exc_info()[0] is not None
        logger.error(f"{self.__class__.__name__}: {message}", exc_info=has_exc)


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
    validated_url = validate_soundcloud_url(track_url)
    active_client_id = client_id or get_cached_client_id()
    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={validated_url}&client_id={active_client_id}"

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
            (data.get("publisher_metadata") or {}).get("artist")
            or (data.get("user") or {}).get("username")
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
                (item.get("publisher_metadata") or {}).get("artist")
                or (item.get("user") or {}).get("username")
                or playlist_artist
            )
            t_duration = item.get("duration", 0)
            t_permalink = item.get("permalink_url") or ""

            t_downloadable = bool(item.get("downloadable")) and bool(item.get("has_downloads_left", True))
            t_transcodings = (item.get("media") or {}).get("transcodings") or []
            has_unenc = any(
                isinstance(tc, dict)
                and (tc.get("format") or {}).get("protocol") in ("progressive", "hls")
                and "encrypted" not in ((tc.get("format") or {}).get("protocol") or "").lower()
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
        (data.get("publisher_metadata") or {}).get("artist")
        or (data.get("user") or {}).get("username")
        or "Onbekende artiest"
    )

    # Artwork: voorkeur 500x500, fallback op wat beschikbaar is
    artwork_url = data.get("artwork_url") or ""
    if artwork_url:
        artwork_url = artwork_url.replace("-large", "-t500x500")

    duration_ms = data.get("duration", 0)
    track_id = data.get("id")
    track_authorization = data.get("track_authorization")
    transcodings = (data.get("media") or {}).get("transcodings") or []

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

    # 2. Bepaal kandidaat-transcodings voor MP3 en M4A
    prog_mp3 = next(
        (
            t for t in transcodings
            if isinstance(t, dict)
            and (t.get("format") or {}).get("protocol") == "progressive"
            and "mpeg" in ((t.get("format") or {}).get("mime_type") or "")
            and "encrypted" not in ((t.get("format") or {}).get("protocol") or "").lower()
        ),
        None,
    )
    hls_mp3 = next(
        (
            t for t in transcodings
            if isinstance(t, dict)
            and (t.get("format") or {}).get("protocol") == "hls"
            and (
                "mpegurl" in ((t.get("format") or {}).get("mime_type") or "")
                or "mpeg" in ((t.get("format") or {}).get("mime_type") or "")
            )
            and "encrypted" not in ((t.get("format") or {}).get("protocol") or "").lower()
        ),
        None,
    )
    prog_m4a = next(
        (
            t for t in transcodings
            if isinstance(t, dict)
            and (t.get("format") or {}).get("protocol") == "progressive"
            and "mp4" in ((t.get("format") or {}).get("mime_type") or "")
            and "encrypted" not in ((t.get("format") or {}).get("protocol") or "").lower()
        ),
        None,
    )
    hls_m4a = next(
        (
            t for t in transcodings
            if isinstance(t, dict)
            and (t.get("format") or {}).get("protocol") == "hls"
            and "mp4" in ((t.get("format") or {}).get("mime_type") or "")
            and "encrypted" not in ((t.get("format") or {}).get("protocol") or "").lower()
        ),
        None,
    )

    # Verzamel unieke kandidaat-transcodings voor parallelle validatie
    candidate_cands = []
    for cand in [prog_mp3, hls_mp3, prog_m4a, hls_m4a]:
        if cand and isinstance(cand, dict) and cand.get("url") and cand not in candidate_cands:
            candidate_cands.append(cand)

    def _validate_transcoding(cand: dict) -> tuple[str, bool]:
        stream_u = cand.get("url")
        if not stream_u:
            return "", False
        try:
            current_cid = get_cached_client_id() or active_client_id
            cdn = get_download_url(
                stream_u,
                client_id=current_cid,
                track_authorization=track_authorization,
                is_direct=False,
            )
            return stream_u, bool(cdn)
        except Exception as exc:
            logger.warning(
                f"Fout bij valideren van transcoding {stream_u}: {exc}",
                exc_info=True,
            )
            return stream_u, False

    valid_stream_urls: set[str] = set()
    if candidate_cands:
        max_workers = min(len(candidate_cands), 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for s_url, is_valid in executor.map(_validate_transcoding, candidate_cands):
                if is_valid and s_url:
                    valid_stream_urls.add(s_url)

    # Werk eventueel de actieve client_id bij als die vernieuwd is tijdens validatie
    refreshed_cid = get_cached_client_id()
    if refreshed_cid:
        active_client_id = refreshed_cid

    # Voeg MP3 toe als optie indien een geldige stream beschikbaar is (progressive heeft voorkeur)
    chosen_mp3 = None
    mp3_protocol = None
    if prog_mp3 and prog_mp3.get("url") in valid_stream_urls:
        chosen_mp3 = prog_mp3
        mp3_protocol = (prog_mp3.get("format") or {}).get("protocol") or "progressive"
    elif hls_mp3 and hls_mp3.get("url") in valid_stream_urls:
        chosen_mp3 = hls_mp3
        mp3_protocol = (hls_mp3.get("format") or {}).get("protocol") or "hls"

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

    # Voeg M4A toe als optie indien een geldige stream beschikbaar is (progressive heeft voorkeur, anders HLS)
    chosen_m4a = None
    m4a_protocol = None
    if prog_m4a and prog_m4a.get("url") in valid_stream_urls:
        chosen_m4a = prog_m4a
        m4a_protocol = (prog_m4a.get("format") or {}).get("protocol") or "progressive"
    elif hls_m4a and hls_m4a.get("url") in valid_stream_urls:
        chosen_m4a = hls_m4a
        m4a_protocol = (hls_m4a.get("format") or {}).get("protocol") or "hls"

    if chosen_m4a:
        available_formats.append({
            "id": "m4a",
            "label": "MP3 (via M4A)",
            "extension": ".mp3",
            "media_type": "audio/mpeg",
            "stream_url": chosen_m4a.get("url"),
            "stream_protocol": m4a_protocol,
            "direct_url": None,
            "is_artist_download": False,
            "is_m4a": True,
        })

    # Foutafhandeling indien er geen enkel ondersteund onbeveiligd formaat beschikbaar is
    if not available_formats:
        format_list = [
            f"{(t.get('format') or {}).get('protocol')} ({(t.get('format') or {}).get('mime_type')})"
            for t in transcodings
            if isinstance(t, dict)
        ]
        print(f"Beschikbare formaten voor '{title}':", format_list)

        has_encrypted = any(
            "encrypted" in ((t.get("format") or {}).get("protocol") or "").lower()
            for t in transcodings
            if isinstance(t, dict)
        )
        has_unencrypted = any(
            isinstance(t, dict)
            and (t.get("format") or {}).get("protocol") in ("progressive", "hls")
            and "encrypted" not in ((t.get("format") or {}).get("protocol") or "").lower()
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

    # Veilige bestandsnaam met juiste extensie via centrale sanitize_filename
    base_candidate = f"{artist} - {title}" if artist else title
    filename = sanitize_filename(base_candidate, extension)

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
        "is_m4a": selected_format.get("is_m4a", False),
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
    if is_direct or not stream_url.startswith("https://api-v2.soundcloud.com/"):
        return validate_cdn_url(stream_url)

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

    return validate_cdn_url(download_url)


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
    for item in (data.get("collection") or []):
        if not isinstance(item, dict):
            continue

        title = item.get("title") or "Onbekende titel"
        artist = (
            (item.get("publisher_metadata") or {}).get("artist")
            or (item.get("user") or {}).get("username")
            or "Onbekende artiest"
        )
        artwork_url = item.get("artwork_url") or ""
        if artwork_url:
            artwork_url = artwork_url.replace("-large", "-t500x500")
        duration_ms = item.get("duration", 0)
        permalink_url = item.get("permalink_url") or ""

        downloadable = bool(item.get("downloadable")) and bool(item.get("has_downloads_left", True))
        transcodings = (item.get("media") or {}).get("transcodings") or []
        has_unencrypted_stream = any(
            isinstance(t, dict)
            and (t.get("format") or {}).get("protocol") in ("progressive", "hls")
            and "encrypted" not in ((t.get("format") or {}).get("protocol") or "").lower()
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
    Controleert CDN-domeinen tegen SSRF en hanteert een maximale streamlimiet van 250 MB.

    Yields:
        Bytes-chunks van het MP3-bestand.

    Raises:
        SoundCloudError: Bij netwerkfouten, SSRF-pogingen of overschrijding van de maximale grootte.
    """
    download_url = validate_cdn_url(download_url)
    clean_url = download_url.split("?")[0].lower()
    is_hls = clean_url.endswith(".m3u8") or ".m3u8" in clean_url or "/hls" in clean_url
    total_streamed = 0

    if is_hls:
        try:
            m3u8_resp = requests.get(download_url, headers=HEADERS, timeout=TIMEOUT)
            m3u8_resp.raise_for_status()
            playlist_text = m3u8_resp.text
        except requests.RequestException as exc:
            raise SoundCloudError(f"Kan HLS playlist niet ophalen: {exc}") from exc

        lines = [line.strip() for line in playlist_text.splitlines() if line.strip()]

        # Controleer op #EXT-X-MAP:URI="..." (het MP4/M4A initialisatiesegment)
        map_match = re.search(r'#EXT-X-MAP:[^\r\n]*URI=["\']?([^"\',\s]+)["\']?', playlist_text, re.IGNORECASE)
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
            init_url = validate_cdn_url(init_url)
            try:
                with requests.get(init_url, headers=HEADERS, stream=True, timeout=TIMEOUT) as init_resp:
                    if init_resp.status_code == 200:
                        for chunk in init_resp.iter_content(chunk_size=1024 * 64):
                            if chunk:
                                total_streamed += len(chunk)
                                if total_streamed > MAX_STREAM_SIZE:
                                    raise SoundCloudError(
                                        "Audiostream overschrijdt de maximale bestandsgrootte van 250 MB."
                                    )
                                yield chunk
                    else:
                        raise SoundCloudError(
                            f"Fout bij downloaden van HLS init-segment: HTTP {init_resp.status_code}"
                        )
            except SoundCloudError:
                raise
            except requests.RequestException as exc:
                raise SoundCloudError(f"Netwerkfout tijdens streamen van init-segment: {exc}") from exc

        def _fetch_segment(seg_url: str) -> bytes:
            seg_url = validate_cdn_url(seg_url)
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
                        total_streamed += len(segment_chunk)
                        if total_streamed > MAX_STREAM_SIZE:
                            raise SoundCloudError(
                                "Audiostream overschrijdt de maximale bestandsgrootte van 250 MB."
                            )
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
                        total_streamed += len(chunk)
                        if total_streamed > MAX_STREAM_SIZE:
                            raise SoundCloudError(
                                "Audiostream overschrijdt de maximale bestandsgrootte van 250 MB."
                            )
                        yield chunk
        except SoundCloudError:
            raise
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


def normalize_audio(
    audio_bytes: bytes,
    extension: str,
    target_extension: str | None = None,
) -> bytes:
    """
    Normaliseert het volume van audio-bytes via FFmpeg met het EBU R128 loudnorm-filter
    (-af loudnorm=I=-14:TP=-1.5:LRA=11).

    Behoudt voor .mp3 een hoge bitrate (-acodec libmp3lame -b:a 256k) en laat lossless
    bestanden (.wav, .flac) hun eigen codec/extensie behouden.
    Wanneer een track van .m4a naar .mp3 moet worden geconverteerd en genormaliseerd,
    gebeurt dit in één enkele FFmpeg-stap om dubbel hercoderen te voorkomen.

    Args:
        audio_bytes: Ruwe binaire inhoud van het audiobestand.
        extension: Extensie van het invoerbestand (bijv. '.mp3', '.m4a', '.wav', '.flac').
        target_extension: Optionele doel-extensie (bijv. '.mp3' bij conversie vanuit '.m4a').

    Returns:
        Binaire inhoud van het genormaliseerde audiobestand.

    Raises:
        SoundCloudError: Als FFmpeg ontbreekt of het normalisatieproces faalt.
    """
    if not audio_bytes:
        raise SoundCloudError("Geen audiogegevens ontvangen voor volume-normalisatie.")

    try:
        ffmpeg_exe = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        logger.error(f"Fout bij bepalen van FFmpeg-pad: {exc}", exc_info=True)
        raise SoundCloudError(f"FFmpeg is niet beschikbaar op het systeem: {exc}") from exc

    if not ffmpeg_exe:
        logger.error("FFmpeg executable niet gevonden via PATH of imageio_ffmpeg.")
        raise SoundCloudError("FFmpeg executable niet gevonden op het systeem.")

    in_ext = ("." + extension.lstrip(".")).lower() if extension else ".mp3"
    if target_extension:
        out_ext = ("." + target_extension.lstrip(".")).lower()
    elif in_ext in (".m4a", ".mp4", ".aac"):
        out_ext = ".mp3"
    else:
        out_ext = in_ext

    with _ffmpeg_semaphore:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                input_file = Path(tmpdir) / f"input{in_ext}"
                output_file = Path(tmpdir) / f"output{out_ext}"

                input_file.write_bytes(audio_bytes)

                cmd = [
                    str(ffmpeg_exe),
                    "-y",
                    "-i",
                    str(input_file),
                    "-vn",
                    "-af",
                    "loudnorm=I=-14:TP=-1.5:LRA=11",
                ]

                if out_ext == ".mp3":
                    cmd.extend(["-acodec", "libmp3lame", "-b:a", "256k"])
                elif out_ext == ".flac":
                    cmd.extend(["-acodec", "flac"])
                elif out_ext == ".wav":
                    cmd.extend(["-acodec", "pcm_s16le"])
                elif out_ext in (".aiff", ".aif"):
                    cmd.extend(["-acodec", "pcm_s16be"])

                cmd.append(str(output_file))

                subprocess.run(cmd, check=True, capture_output=True, shell=False, timeout=120)

                if not output_file.exists():
                    raise SoundCloudError(f"FFmpeg heeft geen output{out_ext} bestand gegenereerd.")

                return output_file.read_bytes()
        except subprocess.TimeoutExpired as exc:
            logger.error("FFmpeg-normalisatie is verlopen na 120 seconden.", exc_info=True)
            raise SoundCloudError("Volume-normalisatie via FFmpeg is verlopen na 120 seconden.") from exc
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
            logger.error(f"FFmpeg-normalisatiefout (exit code {exc.returncode}): {err_msg}", exc_info=True)
            safe_err = re.sub(r"[a-zA-Z]:\\[^\s'\"]+", "[bestand]", err_msg)
            raise SoundCloudError(f"Fout tijdens volume-normalisatie: {safe_err}") from exc
        except SoundCloudError:
            raise
        except Exception as exc:
            logger.error(f"Onverwachte fout tijdens volume-normalisatie: {exc}", exc_info=True)
            raise SoundCloudError("Onverwachte fout tijdens volume-normalisatie.") from exc


def convert_m4a_to_mp3(m4a_bytes: bytes, normalize: bool = False) -> bytes:
    """
    Converteert M4A/AAC audio-bytes naar een standaard MP3-bestand (256 kbps) via FFmpeg.
    Schrijft de input tijdelijk weg in een TemporaryDirectory om fragmented MP4/HLS-headers
    foutloos te ontleden en ruimt alle tijdelijke bestanden na afloop direct automatisch op.
    Indien normalize=True wordt het volume tevens genormaliseerd in één enkele FFmpeg-stap.

    Args:
        m4a_bytes: Ruwe binaire inhoud van het M4A/AAC audiobestand.
        normalize: Indien True, pas tevens EBU R128 volume-normalisatie toe.

    Returns:
        Binaire inhoud van het geconverteerde MP3-bestand.

    Raises:
        SoundCloudError: Als FFmpeg ontbreekt of de audioconversie faalt (wordt gelogd naar error.log).
    """
    if normalize:
        return normalize_audio(m4a_bytes, extension=".m4a", target_extension=".mp3")

    if not m4a_bytes:
        raise SoundCloudError("Geen audiogegevens ontvangen voor M4A-naar-MP3 conversie.")

    try:
        ffmpeg_exe = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        logger.error(f"Fout bij bepalen van FFmpeg-pad: {exc}", exc_info=True)
        raise SoundCloudError(f"FFmpeg is niet beschikbaar op het systeem: {exc}") from exc

    if not ffmpeg_exe:
        logger.error("FFmpeg executable niet gevonden via PATH of imageio_ffmpeg.")
        raise SoundCloudError("FFmpeg executable niet gevonden op het systeem.")

    with _ffmpeg_semaphore:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                input_file = Path(tmpdir) / "input.m4a"
                output_file = Path(tmpdir) / "output.mp3"

                input_file.write_bytes(m4a_bytes)

                cmd = [
                    str(ffmpeg_exe),
                    "-y",
                    "-i",
                    str(input_file),
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    "-b:a",
                    "256k",
                    str(output_file),
                ]

                subprocess.run(cmd, check=True, capture_output=True, shell=False, timeout=120)

                if not output_file.exists():
                    raise SoundCloudError("FFmpeg heeft geen output.mp3 bestand gegenereerd.")

                return output_file.read_bytes()
        except subprocess.TimeoutExpired as exc:
            logger.error("FFmpeg-conversie is verlopen na 120 seconden.", exc_info=True)
            raise SoundCloudError("Audioconversie via FFmpeg is verlopen na 120 seconden.") from exc
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
            logger.error(f"FFmpeg-conversiefout (exit code {exc.returncode}): {err_msg}", exc_info=True)
            safe_err = re.sub(r"[a-zA-Z]:\\[^\s'\"]+", "[bestand]", err_msg)
            raise SoundCloudError(f"Fout tijdens audioconversie naar MP3: {safe_err}") from exc
        except SoundCloudError:
            raise
        except Exception as exc:
            logger.error(f"Onverwachte fout tijdens audioconversie naar MP3: {exc}", exc_info=True)
            raise SoundCloudError("Onverwachte fout tijdens audioconversie naar MP3.") from exc


def download_tracks_as_zip(
    track_urls: list[str],
    client_id: str | None = None,
    normalize: bool = False,
) -> bytes:
    """
    Downloadt meerdere SoundCloud-tracks, voorziet ze van ID3/MP4 metadata en bundelt
    ze in een ZIP-archief. Optioneel kan automatische volume-normalisatie worden toegepast.

    Args:
        track_urls: Lijst van SoundCloud track-URLs.
        client_id: Optionele actieve client_id.
        normalize: Of automatische volume-normalisatie (-14 LUFS) moet worden toegepast.

    Returns:
        Bytes van het gecomprimeerde ZIP-bestand.

    Raises:
        SoundCloudError: Indien er geen tracks gedownload kunnen worden of de limiet overschreden is.
    """
    if not track_urls:
        raise SoundCloudError("Geen tracks opgegeven om te downloaden.")

    if len(track_urls) > MAX_ZIP_TRACKS:
        raise SoundCloudError(
            f"Maximaal {MAX_ZIP_TRACKS} tracks per ZIP-archief toegestaan (ontvangen: {len(track_urls)})."
        )

    # Valideer alle URLs vooraf ter bescherming tegen SSRF
    validated_urls = [validate_soundcloud_url(u) for u in track_urls]

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
            is_m4a = bool(info.get("is_m4a") or info.get("format_id") == "m4a")
            extension = info.get("extension", ".mp3")
            if is_m4a:
                if normalize:
                    raw_audio = normalize_audio(raw_audio, extension=".m4a", target_extension=".mp3")
                else:
                    raw_audio = convert_m4a_to_mp3(raw_audio)
            elif normalize:
                raw_audio = normalize_audio(raw_audio, extension=extension)

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
            for idx, url in enumerate(validated_urls)
        ]
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res is not None:
                indexed_results.append(res)

    indexed_results.sort(key=lambda x: x[0])

    if not indexed_results:
        raise SoundCloudError("Geen van de geselecteerde tracks kon worden gedownload.")

    # Schrijf alle audiobestanden naar een ZIP in het geheugen met veilige bestandsnamen
    zip_buffer = io.BytesIO()
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _, filename, audio_bytes in indexed_results:
            base_filename = os.path.basename(filename)
            base, ext = os.path.splitext(base_filename)
            clean_name = sanitize_filename(base, ext)

            if clean_name in seen_names:
                seen_names[clean_name] += 1
                name_base, name_ext = os.path.splitext(clean_name)
                entry_name = f"{name_base} ({seen_names[clean_name]}){name_ext}"
            else:
                seen_names[clean_name] = 1
                entry_name = clean_name

            zf.writestr(entry_name, audio_bytes)

    return zip_buffer.getvalue()

