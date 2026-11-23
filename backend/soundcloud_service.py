"""
SoundCloud service module.

Bevat alle logica voor het ophalen van de client_id,
track-metadata en de download-URL — zonder enige GUI-afhankelijkheid.
"""

import re
import urllib.parse
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

    # Zoek naar onbeveiligde streams in volgorde van voorkeur (encrypted wordt overgeslagen):
    # 1. progressive met "mpeg" in mime_type (.mp3, audio/mpeg)
    # 2. hls met ("mpegurl" in mime_type of "mpeg" in mime_type) (.mp3, audio/mpeg)
    # 3. hls met "mp4" in mime_type (.m4a, audio/mp4)
    transcodings = data.get("media", {}).get("transcodings", [])
    stream_url = None
    stream_protocol = None
    media_type = None
    extension = None

    # 1. Progressive met "mpeg" in mime_type
    for transcoding in transcodings:
        fmt = transcoding.get("format", {})
        protocol = fmt.get("protocol", "")
        mime = fmt.get("mime_type", "")
        if "encrypted" in protocol.lower():
            continue
        if protocol == "progressive" and "mpeg" in mime:
            stream_url = transcoding.get("url")
            stream_protocol = "progressive"
            media_type = "audio/mpeg"
            extension = ".mp3"
            break

    # 2. HLS met "mpegurl" of "mpeg" in mime_type
    if not stream_url:
        for transcoding in transcodings:
            fmt = transcoding.get("format", {})
            protocol = fmt.get("protocol", "")
            mime = fmt.get("mime_type", "")
            if "encrypted" in protocol.lower():
                continue
            if protocol == "hls" and ("mpegurl" in mime or "mpeg" in mime):
                stream_url = transcoding.get("url")
                stream_protocol = "hls"
                media_type = "audio/mpeg"
                extension = ".mp3"
                break

    # 3. HLS met "mp4" in mime_type
    if not stream_url:
        for transcoding in transcodings:
            fmt = transcoding.get("format", {})
            protocol = fmt.get("protocol", "")
            mime = fmt.get("mime_type", "")
            if "encrypted" in protocol.lower():
                continue
            if protocol == "hls" and "mp4" in mime:
                stream_url = transcoding.get("url")
                stream_protocol = "hls"
                media_type = "audio/mp4"
                extension = ".m4a"
                break

    if not stream_url:
        # Lijst van beschikbare formaten printen naar de terminal
        format_list = [
            f"{t.get('format', {}).get('protocol')} ({t.get('format', {}).get('mime_type')})"
            for t in transcodings
        ]
        print(f"Beschikbare formaten voor '{title}':", format_list)

        # Controleer of er alleen encrypted-hls aanwezig is
        has_encrypted = any("encrypted" in t.get("format", {}).get("protocol", "").lower() for t in transcodings)
        only_encrypted = bool(transcodings) and all("encrypted" in t.get("format", {}).get("protocol", "").lower() for t in transcodings)

        if only_encrypted or (has_encrypted and not any(t.get("format", {}).get("protocol") in ("progressive", "hls") for t in transcodings)):
            raise SoundCloudError(
                f"Deze track ('{title}') is DRM-beveiligd (alleen encrypted-hls beschikbaar) en kan niet worden gedownload."
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
    }


def get_download_url(
    stream_url: str,
    client_id: str,
    track_authorization: str | None = None
) -> str:
    """
    Wisselt de stream-URL in voor de directe CDN-downloadlink.

    Returns:
        De CDN-URL van het MP3-bestand of HLS m3u8 playlist.

    Raises:
        SoundCloudError: Bij netwerk- of API-fouten.
    """
    params = {"client_id": client_id}
    if track_authorization:
        params["track_authorization"] = track_authorization

    try:
        resp = requests.get(stream_url, params=params, headers=HEADERS, timeout=TIMEOUT)
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
