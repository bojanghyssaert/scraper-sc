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
    """Verifieert dat /api/track succesvol metadata teruggeeft."""
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
    }

    with patch("backend.main._get_cached_client_id", return_value="dummy_client_id"), \
         patch("backend.main.get_track_info", return_value=mock_info):

        response = client.get("/api/track?url=https://soundcloud.com/artist/api-track")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "API Track"
        assert data["artist"] == "API Artist"
        assert data["filename"] == "API Artist - API Track.mp3"
        assert data["media_type"] == "audio/mpeg"


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
    """Verifieert dat /api/download audio streamt met correcte headers."""
    mock_info = {
        "title": "Streamed Track",
        "artist": "Streamed Artist",
        "filename": "Streamed Artist - Streamed Track.mp3",
        "media_type": "audio/mpeg",
        "stream_url": "https://api-v2.soundcloud.com/media/stream_dl",
        "stream_protocol": "progressive",
    }

    mock_head = MagicMock()
    mock_head.headers = {"content-length": "1048576"}

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.get_track_info", return_value=mock_info), \
         patch("backend.main.get_download_url", return_value="https://cf-media.sndcdn.com/audio.mp3"), \
         patch("backend.main.req_lib.head", return_value=mock_head), \
         patch("backend.main.stream_audio", return_value=iter([b"fake_mp3_data_chunk_1", b"fake_mp3_data_chunk_2"])):

        response = client.get("/api/download?url=https://soundcloud.com/artist/streamed-track")
        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/mpeg"
        assert 'attachment; filename="Streamed Artist - Streamed Track.mp3"' in response.headers["content-disposition"]
        assert response.headers["content-length"] == "1048576"
        assert response.content == b"fake_mp3_data_chunk_1fake_mp3_data_chunk_2"


def test_api_search_success(client):
    """Verifieert dat /api/search zoekresultaten retourneert."""
    mock_results = [{"id": 1, "title": "Result One"}, {"id": 2, "title": "Result Two"}]

    with patch("backend.main._get_cached_client_id", return_value="dummy_id"), \
         patch("backend.main.search_tracks", return_value=mock_results):

        response = client.get("/api/search?q=ambient")
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["title"] == "Result One"
