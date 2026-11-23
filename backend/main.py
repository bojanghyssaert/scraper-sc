"""
FastAPI backend voor de SoundCloud Downloader webapp.

Endpoints:
    GET /api/track?url=...         — Track- of playlist-metadata ophalen
    GET /api/download?url=...      — Audiobestand streamen (MP3 of M4A)
    GET /api/preview?url=...       — Audio preview streamen voor directe browserweergave
    GET /api/search?q=...          — Tracks zoeken op SoundCloud
    POST /api/download-zip         — Meerdere tracks downloaden als één .zip-bestand
"""

import io
import requests as req_lib
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from backend.soundcloud_service import (
        SoundCloudError,
        SoundCloudDRMError,
        get_client_id,
        get_cached_client_id,
        reset_client_id as service_reset_client_id,
        register_reset_callback,
        register_update_callback,
        get_download_url,
        get_track_info,
        search_tracks,
        stream_audio,
        download_tracks_as_zip,
        embed_metadata,
        HEADERS,
        TIMEOUT,
    )
except ImportError:
    from soundcloud_service import (
        SoundCloudError,
        SoundCloudDRMError,
        get_client_id,
        get_cached_client_id,
        reset_client_id as service_reset_client_id,
        register_reset_callback,
        register_update_callback,
        get_download_url,
        get_track_info,
        search_tracks,
        stream_audio,
        download_tracks_as_zip,
        embed_metadata,
        HEADERS,
        TIMEOUT,
    )

app = FastAPI(title="SoundCloud Downloader API", version="1.0.0")

# CORS: sta de Vite-dev-server toe (inclusief POST voor zip downloads)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Client-ID beheer
_client_id: str | None = None


def reset_client_id() -> None:
    """
    Maakt de gecachete client_id ongeldig in main en soundcloud_service.
    """
    global _client_id
    _client_id = None
    service_reset_client_id()


def _sync_reset() -> None:
    global _client_id
    _client_id = None


def _sync_update(cid: str) -> None:
    global _client_id
    _client_id = cid


register_reset_callback(_sync_reset)
register_update_callback(_sync_update)


def _get_cached_client_id() -> str:
    """
    Haalt de actieve client_id op uit cache of vraagt een nieuwe op.
    """
    global _client_id
    if _client_id is not None:
        return _client_id
    try:
        _client_id = get_cached_client_id()
    except SoundCloudError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return _client_id


@app.get("/api/track")
def track_info(url: str = Query(..., description="Publieke SoundCloud track-URL")):
    """
    Geeft metadata van een SoundCloud-track terug als JSON.

    Response body:
        title               (str)
        artist              (str)
        artwork_url         (str)
        duration_ms         (int)
        filename            (str)  — opgeschoonde MP3- of audiobestandsnaam
        extension           (str)
        media_type          (str)
        is_artist_download  (bool)
        formats             (list) — lijst van beschikbare opties ({id, label, extension})
    """
    client_id = _get_cached_client_id()
    try:
        info = get_track_info(url, client_id)
    except SoundCloudDRMError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if info.get("type") == "playlist":
        return {
            "type": "playlist",
            "title": info["title"],
            "artist": info["artist"],
            "artwork_url": info["artwork_url"],
            "tracks": info["tracks"],
        }

    return {
        "type": "track",
        "title": info["title"],
        "artist": info["artist"],
        "artwork_url": info["artwork_url"],
        "duration_ms": info["duration_ms"],
        "filename": info["filename"],
        "extension": info.get("extension", ".mp3"),
        "media_type": info.get("media_type", "audio/mpeg"),
        "is_artist_download": info.get("is_artist_download", False),
        "formats": info.get("formats", []),
    }


@app.get("/api/download")
def download_track(
    url: str = Query(..., description="Publieke SoundCloud track-URL"),
    format_id: str | None = Query(None, description="ID van het gewenste audioformaat (bijv. mp3, m4a, original)"),
):
    """
    Streamt het audiobestand met metadata en accurate Content-Disposition en Content-Length headers.
    Ondersteunt optionele format_id queryparameter.
    """
    client_id = _get_cached_client_id()

    try:
        info = get_track_info(url, client_id, format_id=format_id)
        if info.get("direct_url"):
            download_url = info["direct_url"]
        else:
            download_url = get_download_url(
                info["stream_url"],
                client_id,
                info.get("track_authorization"),
                is_direct=info.get("stream_protocol") == "direct",
            )
    except SoundCloudDRMError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        chunks = stream_audio(download_url)
        raw_audio = b"".join(chunks)
    except SoundCloudError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    extension = info.get("extension", ".mp3")
    final_audio = embed_metadata(raw_audio, extension, info)

    media_type = info.get("media_type", "audio/mpeg")

    headers = {
        "Content-Disposition": f'attachment; filename="{info["filename"]}"',
        "Content-Length": str(len(final_audio)),
        "Cache-Control": "no-cache",
    }

    return StreamingResponse(
        io.BytesIO(final_audio),
        media_type=media_type,
        headers=headers,
    )


@app.get("/api/preview")
def preview_track(url: str = Query(..., description="Publieke SoundCloud track-URL")):
    """
    Streamt het audiobestand zonder Content-Disposition: attachment header
    voor directe weergave in een HTML5 <audio>-element.
    """
    client_id = _get_cached_client_id()

    try:
        info = get_track_info(url, client_id)
        if info.get("direct_url"):
            download_url = info["direct_url"]
        else:
            download_url = get_download_url(
                info["stream_url"],
                client_id,
                info.get("track_authorization"),
                is_direct=info.get("stream_protocol") == "direct",
            )
    except SoundCloudDRMError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        chunks = stream_audio(download_url)
        raw_audio = b"".join(chunks)
    except SoundCloudError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    media_type = info.get("media_type", "audio/mpeg")

    headers = {
        "Content-Length": str(len(raw_audio)),
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }

    return StreamingResponse(
        io.BytesIO(raw_audio),
        media_type=media_type,
        headers=headers,
    )


@app.get("/api/search")
def search(
    q: str = Query(..., description="Zoekopdracht voor SoundCloud tracks"),
    limit: int = Query(8, description="Aantal zoekresultaten (standaard 8)", ge=1, le=50),
):
    """
    Zoekt tracks op SoundCloud op basis van artiest of titel.
    Geeft een lijst terug van tracks met title, artist, artwork_url, duration_ms, permalink_url en is_drm.
    """
    client_id = _get_cached_client_id()
    try:
        results = search_tracks(q, client_id, limit=limit)
        return {"results": results}
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class DownloadZipRequest(BaseModel):
    playlist_title: str = Field(..., description="Titel van de afspeellijst of het album")
    track_urls: list[str] = Field(..., description="Lijst van SoundCloud track-URLs om te downloaden")


@app.post("/api/download-zip")
def download_zip(payload: DownloadZipRequest):
    """
    Downloadt geselecteerde tracks van een playlist, voorziet ze van metadata-tags,
    bundelt ze in een .zip-archief en retourneert dit via StreamingResponse.
    """
    if not payload.track_urls:
        raise HTTPException(status_code=400, detail="Geen tracks geselecteerd voor download.")

    client_id = _get_cached_client_id()
    try:
        zip_bytes = download_tracks_as_zip(payload.track_urls, client_id)
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    safe_title = "".join(c for c in payload.playlist_title if c.isalnum() or c in " -_").strip()
    safe_title = safe_title or "playlist"
    filename = f"{safe_title}.zip"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(zip_bytes)),
        "Cache-Control": "no-cache",
    }

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers=headers,
    )
