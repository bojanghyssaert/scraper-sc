"""
Gerichte beveiligings- en stabiliteitstests voor SoundCloud Scraper.

Dekt af:
1. SSRF-blokkade bij ongeldige en onveilige URL's.
2. Bestandsnaam-opschoning en Path Traversal-preventie (Windows-namen en ..).
3. Limietcontrole bij te grote ZIP-aanvragen (> 50 tracks) en FFmpeg-timeoutafhandeling.
4. Security-headers en afscherming van interne paden / stacktraces.
"""

import io
import subprocess
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app, reset_client_id, _sanitize_error_detail
from backend.soundcloud_service import (
    SoundCloudError,
    validate_soundcloud_url,
    validate_cdn_url,
    sanitize_filename,
    convert_m4a_to_mp3,
    download_tracks_as_zip,
    stream_audio,
    MAX_ZIP_TRACKS,
    MAX_STREAM_SIZE,
    MAX_FILENAME_LENGTH,
)


@pytest.fixture
def client():
    reset_client_id()
    with patch("backend.main._get_cached_client_id", return_value="dummy_test_cid"), \
         TestClient(app) as test_client:
        yield test_client
    reset_client_id()


# ============================================================================
# 1. SSRF-BLOKKADE & URL-VALIDATIE
# ============================================================================

@pytest.mark.parametrize(
    "invalid_url",
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "file:///C:/Windows/win.ini",
        "file:///etc/passwd",
        "https://evil.com/track",
        "http://soundcloud.com/artist/track",  # Moet HTTPS zijn
        "https://not-soundcloud.com/artist/track",
        "https://soundcloud.com.attacker.com/track",
        "https://169.254.169.254/latest/meta-data",
        "ftp://soundcloud.com/track",
        "javascript:alert(1)",
        "",
        "   ",
    ],
)
def test_validate_soundcloud_url_blocks_ssrf(invalid_url):
    """Verifieert dat ongeldige, lokale of kwaadaardige URL's geblokkeerd worden."""
    with pytest.raises(SoundCloudError):
        validate_soundcloud_url(invalid_url)


@pytest.mark.parametrize(
    "valid_url",
    [
        "https://soundcloud.com/artist/track",
        "https://www.soundcloud.com/artist/track",
        "https://m.soundcloud.com/artist/track",
        "https://on.soundcloud.com/shortlink",
    ],
)
def test_validate_soundcloud_url_allows_legitimate(valid_url):
    """Verifieert dat officiële HTTPS SoundCloud-domeinen worden geaccepteerd."""
    result = validate_soundcloud_url(valid_url)
    assert result == valid_url


def test_validate_cdn_url_blocks_unauthorized_domains():
    """Verifieert dat CDN- en streamvalidatie niet-SoundCloud domeinen weigert."""
    with pytest.raises(SoundCloudError, match="behoort niet tot SoundCloud"):
        validate_cdn_url("https://evil-server.com/malicious.mp3")

    with pytest.raises(SoundCloudError, match="behoort niet tot SoundCloud"):
        validate_cdn_url("http://169.254.169.254/meta-data")

    # Toegestane CDN-domeinen moeten slagen
    assert validate_cdn_url("https://cf-media.sndcdn.com/audio.mp3") == "https://cf-media.sndcdn.com/audio.mp3"
    assert validate_cdn_url("https://api-v2.soundcloud.com/media/stream") == "https://api-v2.soundcloud.com/media/stream"


def test_api_endpoints_reject_ssrf(client):
    """Verifieert dat API-endpoints 400 retourneren bij SSRF-URL's."""
    # /api/track
    resp_track = client.get("/api/track?url=http://localhost:8000")
    assert resp_track.status_code == 400

    # /api/download
    resp_dl = client.get("/api/download?url=file:///C:/Windows/win.ini")
    assert resp_dl.status_code == 400

    # /api/preview
    resp_prev = client.get("/api/preview?url=https://evil.com/track")
    assert resp_prev.status_code == 400

    # /api/download-zip met kwaadaardige URL in lijst
    resp_zip = client.post(
        "/api/download-zip",
        json={
            "playlist_title": "Test Playlist",
            "track_urls": [
                "https://soundcloud.com/artist/legit-track",
                "http://127.0.0.1:8000/internal-admin",
            ],
        },
    )
    assert resp_zip.status_code == 400


# ============================================================================
# 2. BESTANDSNAAM-OPSCHONING & PATH TRAVERSAL PREVENTIE
# ============================================================================

def test_sanitize_filename_path_traversal():
    """Verifieert dat .. en directory separators volledig geneutraliseerd worden."""
    sanitized = sanitize_filename("../../evil", ".mp3")
    assert ".." not in sanitized
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert sanitized == "evil.mp3"

    sanitized_win = sanitize_filename("..\\..\\windows\\system32", ".mp3")
    assert ".." not in sanitized_win
    assert "\\" not in sanitized_win


def test_sanitize_filename_reserved_windows_names():
    """Verifieert dat gereserveerde Windows-bestandsnamen worden aangepast."""
    for res_name in ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"]:
        sanitized = sanitize_filename(res_name, ".mp3")
        base = sanitized.replace(".mp3", "")
        assert base.upper() != res_name
        assert sanitized == f"track_{res_name}.mp3"


def test_sanitize_filename_invalid_characters():
    """Verifieert dat Windows-ongeldige tekens (<>:"/\\|?*) worden vervangen."""
    raw = 'Artist <Remix> : "Great / Song" | Who? *Live*'
    sanitized = sanitize_filename(raw, ".mp3")
    for bad_char in '<>:"/\\|?*':
        assert bad_char not in sanitized


def test_sanitize_filename_length_limit():
    """Verifieert dat de basisbestandsnaam begrensd wordt op maximaal 120 tekens."""
    long_name = "A" * 250
    sanitized = sanitize_filename(long_name, ".mp3")
    base_len = len(sanitized.replace(".mp3", ""))
    assert base_len == MAX_FILENAME_LENGTH
    assert sanitized == ("A" * 120) + ".mp3"


def test_zip_duplicate_and_safe_filenames():
    """Verifieert dat dubbele bestandsnamen in een ZIP netjes (2), (3) krijgen en traversal geweerd wordt."""
    import zipfile

    mock_track = {
        "title": "Duplicate Track",
        "artist": "Artist",
        "filename": "../../Duplicate Track.mp3",
        "extension": ".mp3",
        "stream_url": "https://api-v2.soundcloud.com/media/s1",
        "stream_protocol": "progressive",
    }

    with patch("backend.soundcloud_service.get_track_info", return_value=mock_track), \
         patch("backend.soundcloud_service.get_download_url", return_value="https://cf-media.sndcdn.com/1.mp3"), \
         patch("backend.soundcloud_service.stream_audio", return_value=iter([b"audio_content"])), \
         patch("backend.soundcloud_service.embed_metadata", side_effect=lambda a, e, i: a):

        zip_data = download_tracks_as_zip(
            [
                "https://soundcloud.com/artist/dup-1",
                "https://soundcloud.com/artist/dup-2",
                "https://soundcloud.com/artist/dup-3",
            ],
            client_id="cid",
        )

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            names = zf.namelist()
            assert len(names) == 3
            assert "Duplicate Track.mp3" in names
            assert "Duplicate Track (2).mp3" in names
            assert "Duplicate Track (3).mp3" in names
            # Geen directory traversal
            for name in names:
                assert ".." not in name
                assert "/" not in name
                assert "\\" not in name


# ============================================================================
# 3. RESOURCE-LIMIETEN & FFMPEG-BEVEILIGING
# ============================================================================

def test_download_zip_max_tracks_limit(client):
    """Verifieert dat ZIP-aanvragen met meer dan 50 tracks geweigerd worden."""
    urls = [f"https://soundcloud.com/artist/track-{i}" for i in range(51)]

    # Directe service call
    with pytest.raises(SoundCloudError, match="Maximaal 50 tracks"):
        download_tracks_as_zip(urls, client_id="cid")

    # API call
    resp = client.post(
        "/api/download-zip",
        json={"playlist_title": "Too Large", "track_urls": urls},
    )
    assert resp.status_code in (400, 422)


def test_ffmpeg_timeout_handling():
    """Verifieert dat een FFmpeg timeout (120s) resulteert in een nette SoundCloudError."""
    with patch("shutil.which", return_value="ffmpeg"), \
         patch(
             "subprocess.run",
             side_effect=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=120),
         ):
        with pytest.raises(SoundCloudError, match="verlopen na 120 seconden"):
            convert_m4a_to_mp3(b"fake_m4a_audio_bytes")


def test_stream_audio_max_size_limit():
    """Verifieert dat een stream die de limiet van 250 MB overschrijdt wordt afgebroken."""
    # Chunk van 10 MB, 26 chunks = 260 MB (> 250 MB)
    large_chunk = b"X" * (10 * 1024 * 1024)
    chunks_generator = (large_chunk for _ in range(26))

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_content.return_value = chunks_generator
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("backend.soundcloud_service.requests.get", return_value=mock_resp):
        with pytest.raises(SoundCloudError, match="maximale.*250 MB"):
            list(stream_audio("https://cf-media.sndcdn.com/huge.mp3"))


# ============================================================================
# 4. API-HARDENING & VEILIGE FOUTMELDINGEN
# ============================================================================

def test_security_headers_present_in_responses(client):
    """Verifieert dat alle security headers aanwezig zijn in API-antwoorden."""
    with patch("backend.main.search_tracks", return_value=[]):
        resp = client.get("/api/search?q=test")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"


def test_error_detail_sanitizer_removes_windows_paths():
    """Verifieert dat Windows-paden en tracebacks uit foutmeldingen gefilterd worden."""
    sensitive_msg = (
        r"Fout opgetreden in C:\Users\Admin\SecretProject\backend\main.py regel 42: "
        r"bestand C:\Windows\System32\drivers\etc\hosts niet gevonden"
    )
    sanitized = _sanitize_error_detail(sensitive_msg)
    assert r"C:\Users" not in sanitized
    assert r"C:\Windows" not in sanitized
    assert "[bestand]" in sanitized


def test_search_query_validation(client):
    """Verifieert dat lege zoektermen of zoektermen > 120 tekens worden afgewezen."""
    # Lege zoekterm
    resp_empty = client.get("/api/search?q=")
    assert resp_empty.status_code in (400, 422)

    resp_spaces = client.get("/api/search?q=   ")
    assert resp_spaces.status_code in (400, 422)

    # Te lange zoekterm (> 120 tekens)
    resp_long = client.get(f"/api/search?q={'a' * 121}")
    assert resp_long.status_code in (400, 422)

    # Geldige zoekterm
    with patch("backend.main.search_tracks", return_value=[]):
        resp_valid = client.get("/api/search?q=legit+search")
        assert resp_valid.status_code == 200
