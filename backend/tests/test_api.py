"""
API tests voor backend/main.py met FastAPI TestClient.

Alle SoundCloud-interacties worden gemockt volgens de quality-assurance richtlijnen.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app, reset_client_id
from backend.soundcloud_service import SoundCloudError, SoundCloudDRMError


@pytest.fixture
def client():
    reset_client_id()
    with TestClient(app) as test_client:
        yield test_client
    reset_client_id()


def test_api_track_success(client):
    """Verifieert dat /api/track succesvol metadata en formaten teruggeeft."""
    mock_info = {
        "title": "API Track",
        "artist": "API Artist",
        "artwork_url": "https://i1.sndcdn.com/artworks-api-t500x500.jpg",
        "duration_ms": 150000,
        "filename": "API Artist - API Track.mp3",
        "extension": ".mp3",
        "media_type": "audio/mpeg",
        "is_artist_download": False,
        "stream_url": "https://api-v2.soundcloud.com/media/dummy",
        "formats": [
            {"id": "mp3", "label": "MP3 (Standaard)", "extension": ".mp3"},
            {"id": "m4a", "label": "M4A (Hoge kwaliteit)", "extension": ".m4a"},
        ],
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_client_id"), \
         patch("backend.main.get_track_info", return_value=mock_info) as mock_get_info:

        response = client.get("/api/track?url=https://soundcloud.com/artist/api-track")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "API Track"
        assert data["artist"] == "API Artist"
        assert data["filename"] == "API Artist - API Track.mp3"
        assert data["media_type"] == "audio/mpeg"
        assert "formats" in data
        assert len(data["formats"]) == 2
        assert data["formats"][0]["id"] == "mp3"
        assert data["formats"][0]["label"] == "MP3 (Standaard)"
        assert data["formats"][1]["id"] == "m4a"
        mock_get_info.assert_called_once_with("https://soundcloud.com/artist/api-track", "dummy_client_id")


def test_api_track_auto_refreshes_expired_client_id(client):
    """
    Verifieert dat wanneer de client_id verlopen is (401 bij SoundCloud),
    de backend dit automatisch afhandelt en de gebruiker direct een succesvol 200-antwoord krijgt.
    """
    mock_401 = MagicMock()
    mock_401.status_code = 401

    mock_200_resolve = MagicMock()
    mock_200_resolve.status_code = 200
    mock_200_resolve.json.return_value = {
        "title": "Auto Refresh Track",
        "user": {"username": "Producer"},
        "artwork_url": "https://i1.sndcdn.com/artworks-refresh-large.jpg",
        "duration": 200000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/stream_refresh",
                }
            ]
        },
    }

    mock_200_stream = MagicMock()
    mock_200_stream.status_code = 200
    mock_200_stream.json.return_value = {"url": "https://cf-media.sndcdn.com/audio_refresh.mp3"}

    with patch("backend.soundcloud_service.get_client_id", return_value="fresh_api_cid_123") as mock_get_cid, \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_401, mock_200_resolve, mock_200_stream]):

        response = client.get("/api/track?url=https://soundcloud.com/producer/auto-refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Auto Refresh Track"
        assert data["artist"] == "Producer"
        assert mock_get_cid.call_count >= 1


def test_api_track_not_found(client):
    """Verifieert dat een onbekende track resulteert in een 400 foutmelding."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", side_effect=SoundCloudError("Track niet gevonden. Controleer de URL.")):

        response = client.get("/api/track?url=https://soundcloud.com/artist/nonexistent")
        assert response.status_code == 400
        assert "Track niet gevonden" in response.json()["detail"]


def test_api_track_drm_protected(client):
    """Verifieert dat een DRM-beveiligde track HTTP 403 teruggeeft."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", side_effect=SoundCloudDRMError("Dit nummer is DRM-beveiligd")):

        response = client.get("/api/track?url=https://soundcloud.com/artist/drm-protected")
        assert response.status_code == 403
        assert "DRM-beveiligd" in response.json()["detail"]


def test_api_download_success(client):
    """Verifieert dat /api/download audio streamt met accurate Content-Length en metadata."""
    import io
    from mutagen.id3 import ID3

    mock_info = {
        "title": "Streamed Track",
        "artist": "Streamed Artist",
        "filename": "Streamed Artist - Streamed Track.mp3",
        "media_type": "audio/mpeg",
        "extension": ".mp3",
        "stream_url": "https://api-v2.soundcloud.com/media/stream_dl",
        "stream_protocol": "progressive",
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", return_value=mock_info), \
         patch("backend.main.get_download_url", return_value="https://cf-media.sndcdn.com/audio.mp3"), \
         patch("backend.main.stream_audio", return_value=iter([b"fake_mp3_data_chunk_1", b"fake_mp3_data_chunk_2"])):

        response = client.get("/api/download?url=https://soundcloud.com/artist/streamed-track")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert 'attachment; filename="Streamed Artist - Streamed Track.mp3"' in response.headers["content-disposition"]
        assert response.headers["content-length"] == str(len(response.content))
        assert b"fake_mp3_data_chunk_1fake_mp3_data_chunk_2" in response.content

        # Verifieer ID3-tags in de geretourneerde response-bytes
        tags = ID3(io.BytesIO(response.content))
        assert str(tags.get("TIT2")) == "Streamed Track"
        assert str(tags.get("TPE1")) == "Streamed Artist"


def test_api_download_with_format_id(client):
    """Verifieert dat /api/download de format_id parameter doorgeeft aan get_track_info."""
    mock_info = {
        "title": "Streamed M4A Track",
        "artist": "Streamed Artist",
        "filename": "Streamed Artist - Streamed M4A Track.m4a",
        "media_type": "audio/mp4",
        "extension": ".m4a",
        "stream_url": "https://api-v2.soundcloud.com/media/stream_m4a",
        "stream_protocol": "hls",
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", return_value=mock_info) as mock_get_info, \
         patch("backend.main.get_download_url", return_value="https://cf-media.sndcdn.com/playlist.m3u8"), \
         patch("backend.main.stream_audio", return_value=iter([b"fake_m4a_chunk"])):

        response = client.get("/api/download?url=https://soundcloud.com/artist/m4a-track&format_id=m4a")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mp4"
        assert 'attachment; filename="Streamed Artist - Streamed M4A Track.m4a"' in response.headers["content-disposition"]
        mock_get_info.assert_called_once_with(
            "https://soundcloud.com/artist/m4a-track",
            "dummy_id",
            format_id="m4a",
        )


def test_api_download_invalid_format_id(client):
    """Verifieert dat een ongeldig format_id resulteert in HTTP 400."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", side_effect=SoundCloudError("Formaat 'flac' is niet beschikbaar")):

        response = client.get("/api/download?url=https://soundcloud.com/artist/track&format_id=flac")
        assert response.status_code == 400
        assert "Formaat 'flac' is niet beschikbaar" in response.json()["detail"]


def test_api_search_success(client):
    """Verifieert dat /api/search zoekresultaten retourneert met juiste velden."""
    mock_results = [
        {
            "title": "Search Track 1",
            "artist": "Search Artist 1",
            "artwork_url": "https://i1.sndcdn.com/artworks-1-t500x500.jpg",
            "duration_ms": 180000,
            "permalink_url": "https://soundcloud.com/artist/track-1",
            "is_drm": False,
        },
        {
            "title": "Search Track 2 (DRM)",
            "artist": "Search Artist 2",
            "artwork_url": "https://i1.sndcdn.com/artworks-2-t500x500.jpg",
            "duration_ms": 210000,
            "permalink_url": "https://soundcloud.com/artist/track-2",
            "is_drm": True,
        },
    ]

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.search_tracks", return_value=mock_results) as mock_search:

        response = client.get("/api/search?q=ambient&limit=5")
        assert response.status_code == 200
        mock_search.assert_called_once_with("ambient", "dummy_id", limit=5)
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["title"] == "Search Track 1"
        assert data["results"][0]["is_drm"] is False
        assert data["results"][1]["is_drm"] is True


def test_api_search_error(client):
    """Verifieert dat /api/search HTTP 400 retourneert als SoundCloudError optreedt."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.search_tracks", side_effect=SoundCloudError("Fout bij zoeken op SoundCloud")):

        response = client.get("/api/search?q=faulty")
        assert response.status_code == 400
        assert "Fout bij zoeken op SoundCloud" in response.json()["detail"]


def test_api_preview_success(client):
    """Verifieert dat /api/preview audio streamt zonder Content-Disposition attachment."""
    mock_info = {
        "title": "Preview Track",
        "artist": "Preview Artist",
        "filename": "Preview Artist - Preview Track.mp3",
        "media_type": "audio/mpeg",
        "extension": ".mp3",
        "stream_url": "https://api-v2.soundcloud.com/media/stream_prev",
        "stream_protocol": "progressive",
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", return_value=mock_info), \
         patch("backend.main.get_download_url", return_value="https://cf-media.sndcdn.com/preview.mp3"), \
         patch("backend.main.stream_audio", return_value=iter([b"preview_chunk_1", b"preview_chunk_2"])):

        response = client.get("/api/preview?url=https://soundcloud.com/artist/preview-track")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert "content-disposition" not in response.headers
        assert response.headers["content-length"] == str(len(b"preview_chunk_1preview_chunk_2"))
        assert response.headers.get("accept-ranges") == "bytes"
        assert response.content == b"preview_chunk_1preview_chunk_2"


def test_api_preview_not_found(client):
    """Verifieert dat /api/preview 400 retourneert als de track niet gevonden wordt."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", side_effect=SoundCloudError("Track niet gevonden")):

        response = client.get("/api/preview?url=https://soundcloud.com/artist/nonexistent")
        assert response.status_code == 400
        assert "Track niet gevonden" in response.json()["detail"]


def test_api_preview_drm_protected(client):
    """Verifieert dat /api/preview 403 retourneert bij DRM-beveiligde tracks."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", side_effect=SoundCloudDRMError("DRM-beveiligd")):

        response = client.get("/api/preview?url=https://soundcloud.com/artist/drm-protected")
        assert response.status_code == 403
        assert "DRM-beveiligd" in response.json()["detail"]


def test_api_preview_stream_error(client):
    """Verifieert dat /api/preview 502 retourneert als stream_audio faalt."""
    mock_info = {
        "title": "Error Track",
        "artist": "Error Artist",
        "filename": "Error Artist - Error Track.mp3",
        "media_type": "audio/mpeg",
        "extension": ".mp3",
        "stream_url": "https://api-v2.soundcloud.com/media/stream_err",
        "stream_protocol": "progressive",
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", return_value=mock_info), \
         patch("backend.main.get_download_url", return_value="https://cf-media.sndcdn.com/error.mp3"), \
         patch("backend.main.stream_audio", side_effect=SoundCloudError("Stream netwerkfout")):

        response = client.get("/api/preview?url=https://soundcloud.com/artist/stream-error")
        assert response.status_code == 502
        assert "Stream netwerkfout" in response.json()["detail"]


def test_api_track_playlist_success(client):
    """Verifieert dat /api/track playlist-metadata en tracks retourneert bij kind=playlist."""
    mock_playlist_info = {
        "type": "playlist",
        "title": "Summer Vibes Set",
        "artist": "DJ Chill",
        "artwork_url": "https://i1.sndcdn.com/artworks-playlist-t500x500.jpg",
        "tracks": [
            {
                "url": "https://soundcloud.com/dj-chill/track-1",
                "title": "Track 1",
                "artist": "DJ Chill",
                "duration_ms": 180000,
                "downloadable": True,
                "is_drm": False,
            },
            {
                "url": "https://soundcloud.com/dj-chill/track-2",
                "title": "Track 2",
                "artist": "DJ Chill",
                "duration_ms": 200000,
                "downloadable": False,
                "is_drm": True,
            },
        ],
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_cid"), \
         patch("backend.main.get_track_info", return_value=mock_playlist_info):

        response = client.get("/api/track?url=https://soundcloud.com/dj-chill/sets/summer-vibes")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "playlist"
        assert data["title"] == "Summer Vibes Set"
        assert data["artist"] == "DJ Chill"
        assert len(data["tracks"]) == 2
        assert data["tracks"][0]["title"] == "Track 1"
        assert data["tracks"][0]["is_drm"] is False
        assert data["tracks"][1]["is_drm"] is True


def test_api_download_zip_success(client):
    """Verifieert dat POST /api/download-zip een ZIP-bestand streamt met Content-Disposition."""
    import zipfile
    import io

    # Bouw een dummy zip
    dummy_zip_buf = io.BytesIO()
    with zipfile.ZipFile(dummy_zip_buf, "w") as zf:
        zf.writestr("Track 1.mp3", b"audio_content")
    dummy_zip_bytes = dummy_zip_buf.getvalue()

    with patch("backend.main._get_cached_client_id", return_value="dummy_cid"), \
         patch("backend.main.download_tracks_as_zip", return_value=dummy_zip_bytes):

        payload = {
            "playlist_title": "Summer Vibes Set",
            "track_urls": [
                "https://soundcloud.com/dj-chill/track-1",
            ],
        }
        response = client.post("/api/download-zip", json=payload)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert 'attachment; filename="Summer Vibes Set.zip"' in response.headers["content-disposition"]
        assert response.headers["content-length"] == str(len(dummy_zip_bytes))
        assert response.content == dummy_zip_bytes


def test_api_download_zip_empty_urls(client):
    """Verifieert dat POST /api/download-zip 400 retourneert bij een lege track_urls lijst."""
    payload = {
        "playlist_title": "Empty Set",
        "track_urls": [],
    }
    response = client.post("/api/download-zip", json=payload)
    assert response.status_code == 400
    assert "Geen tracks geselecteerd" in response.json()["detail"]


def test_api_download_zip_error(client):
    """Verifieert dat POST /api/download-zip 400 retourneert als download_tracks_as_zip faalt."""
    with patch("backend.main._get_cached_client_id", return_value="dummy_cid"), \
         patch("backend.main.download_tracks_as_zip", side_effect=SoundCloudError("Fout bij downloaden van tracks")):

        payload = {
            "playlist_title": "Faulty Set",
            "track_urls": ["https://soundcloud.com/faulty/1"],
        }
        response = client.post("/api/download-zip", json=payload)
        assert response.status_code == 400
        assert "Fout bij downloaden" in response.json()["detail"]


def test_global_exception_handler_catches_unhandled_error():
    """Verifieert dat onverwachte exceptions worden opgevangen en gelogd naar error.log met status 500."""
    with TestClient(app, raise_server_exceptions=False) as no_raise_client:
        with patch("backend.main._get_cached_client_id", return_value="dummy_cid"), \
             patch("backend.main.get_track_info", side_effect=RuntimeError("Onverwachte crash in service")):
            response = no_raise_client.get("/api/track?url=https://soundcloud.com/test/track")
            assert response.status_code == 500
            assert "interne serverfout" in response.json()["detail"].lower()


def test_validation_error_handler_logs_422(client):
    """Verifieert dat ontbrekende verplichte query-parameters (422) netjes worden gelogd."""
    response = client.get("/api/track")
    assert response.status_code == 422
    assert "detail" in response.json()


def test_logger_configuration():
    """Verifieert dat RotatingFileHandler correct is geconfigureerd (max 1MB, UTF-8, timestamp en bestandsnaam)."""
    from logging.handlers import RotatingFileHandler
    from backend.main import logger, LOGS_DIR

    assert LOGS_DIR.exists()
    assert LOGS_DIR.is_dir()

    handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(handlers) >= 1
    handler = handlers[0]
    assert handler.maxBytes == 1024 * 1024
    assert handler.encoding == "utf-8"

    fmt = handler.formatter._fmt
    assert "%(asctime)s" in fmt
    assert "%(levelname)s" in fmt
    assert "%(filename)s" in fmt


def test_error_log_file_contains_entries():
    """Verifieert dat fouten daadwerkelijk naar logs/error.log geschreven worden."""
    from backend.main import ERROR_LOG_FILE
    assert ERROR_LOG_FILE.exists()
    content = ERROR_LOG_FILE.read_text(encoding="utf-8")
    assert "Onverwachte crash in service" in content
    assert "RuntimeError" in content
