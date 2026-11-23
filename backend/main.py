"""
FastAPI backend voor de SoundCloud Downloader webapp.

Endpoints:
    GET /api/track?url=...     — Track-metadata ophalen
    GET /api/download?url=...  — MP3-bestand streamen
"""

import requests as req_lib
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from soundcloud_service import (
    SoundCloudError,
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
        title        (str)
        artist       (str)
        artwork_url  (str)
        duration_ms  (int)
        filename     (str)  — opgeschoonde MP3-bestandsnaam
    """
    client_id = _get_cached_client_id()
    try:
        info = get_track_info(url, client_id)
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "title": info["title"],
        "artist": info["artist"],
        "artwork_url": info["artwork_url"],
        "duration_ms": info["duration_ms"],
        "filename": info["filename"],
    }


@app.get("/api/download")
def download_track(url: str = Query(..., description="Publieke SoundCloud track-URL")):
    """
    Streamt het MP3-bestand met de juiste Content-Disposition en Content-Length headers.
    """
    client_id = _get_cached_client_id()

    try:
        info = get_track_info(url, client_id)
        download_url = get_download_url(info["stream_url"], client_id)
    except SoundCloudError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Content-Length ophalen voor voortgangsbalk in de frontend
    content_length = None
    try:
        head_resp = req_lib.head(download_url, headers=HEADERS, timeout=TIMEOUT)
        cl = head_resp.headers.get("content-length")
        if cl and cl.isdigit():
            content_length = int(cl)
    except Exception:
        pass  # Content-Length is optioneel; stream gaat door zonder

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
        media_type="audio/mpeg",
        headers=headers,
    )
