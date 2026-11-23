"""
FastAPI backend voor de SoundCloud Downloader webapp.

Endpoints:
    GET /api/track?url=...     — Track-metadata ophalen
    GET /api/download?url=...  — Audiobestand streamen (MP3 of M4A)
    GET /api/search?q=...      — Tracks zoeken op SoundCloud
"""

import io
import requests as req_lib
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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
        embed_metadata,
        HEADERS,
        TIMEOUT,
    )

app = FastAPI(title="SoundCloud Downloader API", version="1.0.0")

# CORS: sta de Vite-dev-server toe
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
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
    """
    client_id = _get_cached_client_id()
    try:
        info = get_track_info(url, client_id)
    except SoundCloudDRMError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "title": info["title"],
        "artist": info["artist"],
        "artwork_url": info["artwork_url"],
        "duration_ms": info["duration_ms"],
        "filename": info["filename"],
        "extension": info.get("extension", ".mp3"),
        "media_type": info.get("media_type", "audio/mpeg"),
        "is_artist_download": info.get("is_artist_download", False),
    }


@app.get("/api/download")
def download_track(url: str = Query(..., description="Publieke SoundCloud track-URL")):
    """
    Streamt het audiobestand met metadata en accurate Content-Disposition en Content-Length headers.
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


@app.get("/api/search")
def search(q: str = Query(..., description="Zoekopdracht voor SoundCloud tracks")):
    """
    Zoekt tracks op SoundCloud op basis van een zoekopdracht.
    """
    client_id = _get_cached_client_id()
    try:
        results = search_tracks(q, client_id)
        return {"results": results}
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
