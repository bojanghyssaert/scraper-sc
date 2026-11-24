"""
SoundCloud scraping en metadata extractie voor tracks, afspeellijsten en zoeken.
"""

import concurrent.futures
import sys

from .constants import HEADERS, TIMEOUT
from .exceptions import SoundCloudDRMError, SoundCloudError
from .logging_config import logger
from .security import sanitize_filename, validate_soundcloud_url
from . import client as client_mod
from . import downloader as downloader_mod


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
    get_cached_fn = getattr(client_mod, "get_cached_client_id", client_mod.get_cached_client_id)
    fetch_fn = getattr(client_mod, "_fetch_with_retry", client_mod._fetch_with_retry)

    active_client_id = client_id or get_cached_fn()
    resolve_url = f"https://api-v2.soundcloud.com/resolve?url={validated_url}&client_id={active_client_id}"

    resp, active_client_id = fetch_fn(resolve_url, client_id=active_client_id)

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
                    b_resp, active_client_id = fetch_fn(
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
            dl_resp, active_client_id = fetch_fn(dl_api_url, client_id=active_client_id)
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
            current_cid = get_cached_fn() or active_client_id
            fn_get_dl = getattr(downloader_mod, "get_download_url", downloader_mod.get_download_url)
            cdn = fn_get_dl(
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
    refreshed_cid = get_cached_fn()
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

    fetch_fn = getattr(client_mod, "_fetch_with_retry", client_mod._fetch_with_retry)
    resp, _ = fetch_fn(
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
