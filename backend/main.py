"""
FastAPI backend voor de SoundCloud Downloader webapp.

Endpoints:
    GET /api/track?url=...     — Track-metadata ophalen
    GET /api/download?url=...  — Audiobestand streamen (MP3 of M4A)
"""

import requests as req_lib
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

try:
    from backend.soundcloud_service import (
        SoundCloudError,
        SoundCloudDRMError,
        get_client_id,
        get_download_url,
        get_track_info,
        stream_audio,
        HEADERS,
        TIMEOUT,
    )
except ImportError:
    from soundcloud_service import (
        SoundCloudError,
        SoundCloudDRMError,
        get_client_id,
        get_download_url,
        get_track_info,
        stream_audio,
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

# Client-ID wordt éénmalig opgehaald bij eerste request (lazy init)
_client_id: str | None = None


def _get_cached_client_id() -> str:
    global _client_id
    if _client_id is None:
        try:
            _client_id = get_client_id()
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
    Streamt het audiobestand met de juiste Content-Disposition en Content-Length headers.
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

    clean_url = download_url.split("?")[0].lower()
    is_hls = clean_url.endswith(".m3u8") or ".m3u8" in clean_url or "/hls" in clean_url

    # Content-Length alleen ophalen voor progressive streams (bij HLS m3u8 is dit de playlist-grootte)
    content_length = None
    if not is_hls:
        try:
            head_resp = req_lib.head(download_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            cl = head_resp.headers.get("content-length")
            if cl and cl.isdigit():
                content_length = int(cl)
        except Exception:
            pass  # Content-Length is optioneel; stream gaat door zonder

    media_type = info.get("media_type", "audio/mpeg")

    headers = {
        "Content-Disposition": f'attachment; filename="{info["filename"]}"',
        "Cache-Control": "no-cache",
    }
    if content_length:
        headers["Content-Length"] = str(content_length)

    try:
        generator = stream_audio(download_url)
    except SoundCloudError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return StreamingResponse(
        generator,
        media_type=media_type,
        headers=headers,
    )
