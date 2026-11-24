"""
Audio streaming, CDN-download link resolutie en ZIP-bundeling.
"""

import concurrent.futures
import io
import os
import re
import sys
import urllib.parse
import zipfile
import requests

from .constants import HEADERS, MAX_STREAM_SIZE, MAX_ZIP_TRACKS, TIMEOUT
from .exceptions import SoundCloudError
from .security import sanitize_filename, validate_cdn_url, validate_soundcloud_url
from . import client as client_mod
from . import media as media_mod


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

    fetch_fn = getattr(client_mod, "_fetch_with_retry", client_mod._fetch_with_retry)
    resp, _ = fetch_fn(
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

    get_cached_fn = getattr(client_mod, "get_cached_client_id", client_mod.get_cached_client_id)
    active_client_id = client_id or get_cached_fn()

    from . import scraper as scraper_mod
    this_mod = sys.modules[__name__]

    def _download_one(index: int, url: str) -> tuple[int, str, bytes] | None:
        try:
            fn_get_info = getattr(scraper_mod, "get_track_info", scraper_mod.get_track_info)
            info = fn_get_info(url, active_client_id)
            if info.get("type") == "playlist":
                return None
            if info.get("direct_url"):
                dl_url = info["direct_url"]
            else:
                fn_get_dl = getattr(this_mod, "get_download_url", get_download_url)
                dl_url = fn_get_dl(
                    info["stream_url"],
                    active_client_id,
                    info.get("track_authorization"),
                    is_direct=info.get("stream_protocol") == "direct",
                )
            fn_stream = getattr(this_mod, "stream_audio", stream_audio)
            chunks = fn_stream(dl_url)
            raw_audio = b"".join(chunks)
            is_m4a = bool(info.get("is_m4a") or info.get("format_id") == "m4a")
            extension = info.get("extension", ".mp3")
            if is_m4a:
                if normalize:
                    fn_norm = getattr(media_mod, "normalize_audio", media_mod.normalize_audio)
                    raw_audio = fn_norm(raw_audio, extension=".m4a", target_extension=".mp3")
                else:
                    fn_conv = getattr(media_mod, "convert_m4a_to_mp3", media_mod.convert_m4a_to_mp3)
                    raw_audio = fn_conv(raw_audio)
            elif normalize:
                fn_norm = getattr(media_mod, "normalize_audio", media_mod.normalize_audio)
                raw_audio = fn_norm(raw_audio, extension=extension)

            fn_embed = getattr(media_mod, "embed_metadata", media_mod.embed_metadata)
            final_audio = fn_embed(raw_audio, extension, info)
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
