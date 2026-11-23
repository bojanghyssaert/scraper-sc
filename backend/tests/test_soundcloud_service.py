"""
Unit tests voor backend/soundcloud_service.py.

Alle SoundCloud-aanroepen worden gemockt; er vinden geen echte netwerkverzoeken plaats.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from backend.soundcloud_service import (
    SoundCloudError,
    SoundCloudDRMError,
    get_cached_client_id,
    reset_client_id,
    get_track_info,
    get_download_url,
    search_tracks,
    stream_audio,
    _cached_client_id,
)


@pytest.fixture(autouse=True)
def clean_client_id_cache():
    """Zorg voor een schone client_id cache voor en na elke test."""
    reset_client_id()
    yield
    reset_client_id()


def test_reset_client_id():
    """Verifieert dat reset_client_id() de gecachete client_id leegmaakt."""
    from backend import soundcloud_service
    soundcloud_service._cached_client_id = "test_client_id_123"
    reset_client_id()
    assert soundcloud_service._cached_client_id is None


def test_get_cached_client_id_caching():
    """Verifieert dat get_cached_client_id() get_client_id() aanroept en cachet."""
    with patch("backend.soundcloud_service.get_client_id", return_value="fresh_client_id_12345678901234") as mock_fetch:
        cid1 = get_cached_client_id()
        cid2 = get_cached_client_id()
        assert cid1 == "fresh_client_id_12345678901234"
        assert cid2 == cid1
        assert mock_fetch.call_count == 1


def test_get_track_info_auto_refresh_on_401():
    """
    Simuleert een 401-fout bij /resolve en verifieert dat de client_id
    automatisch wordt vernieuwd en de tweede poging slaagt.
    """
    mock_401 = MagicMock()
    mock_401.status_code = 401

    mock_200_resolve = MagicMock()
    mock_200_resolve.status_code = 200
    mock_200_resolve.json.return_value = {
        "title": "Test Track",
        "user": {"username": "Test Artist"},
        "artwork_url": "https://i1.sndcdn.com/artworks-test-large.jpg",
        "duration": 180000,
        "id": 123456,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/stream1",
                }
            ]
        },
    }

    mock_200_stream = MagicMock()
    mock_200_stream.status_code = 200
    mock_200_stream.json.return_value = {"url": "https://cdn.example.com/stream.mp3"}

    # Volgorde:
    # 1. /resolve met verlopen client_id -> 401
    # 2. /resolve met verse client_id -> 200
    # 3. Stream-validatiecheck -> 200
    with patch("backend.soundcloud_service.get_client_id", return_value="new_fresh_id_1234567890123456") as mock_get_cid, \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_401, mock_200_resolve, mock_200_stream]) as mock_req:

        info = get_track_info("https://soundcloud.com/test/track", client_id="expired_id_123")

        assert mock_get_cid.call_count == 1
        assert info["title"] == "Test Track"
        assert info["artist"] == "Test Artist"
        assert info["stream_url"] == "https://api-v2.soundcloud.com/media/stream1"
        assert info["media_type"] == "audio/mpeg"

        # Controleer dat de 2e aanroep van requests.get de nieuwe client_id bevatte
        second_call = mock_req.call_args_list[1]
        assert "new_fresh_id_1234567890123456" in second_call[0][0] or (
            second_call[1].get("params") and second_call[1]["params"].get("client_id") == "new_fresh_id_1234567890123456"
        )


def test_get_track_info_auto_refresh_on_403():
    """Simuleert een 403-fout bij /resolve en verifieert automatische vernieuwing."""
    mock_403 = MagicMock()
    mock_403.status_code = 403

    mock_200_resolve = MagicMock()
    mock_200_resolve.status_code = 200
    mock_200_resolve.json.return_value = {
        "title": "403 Test Track",
        "user": {"username": "Test Artist"},
        "duration": 60000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/stream2",
                }
            ]
        },
    }

    mock_200_stream = MagicMock()
    mock_200_stream.status_code = 200
    mock_200_stream.json.return_value = {"url": "https://cdn.example.com/stream2.mp3"}

    with patch("backend.soundcloud_service.get_client_id", return_value="fresh_id_403") as mock_get_cid, \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_403, mock_200_resolve, mock_200_stream]):

        info = get_track_info("https://soundcloud.com/test/track403")
        assert mock_get_cid.call_count >= 1
        assert info["title"] == "403 Test Track"


def test_get_track_info_persistent_401_raises_error():
    """Verifieert dat bij aanhoudende 401 na refresh een SoundCloudError wordt gegooid."""
    mock_401 = MagicMock()
    mock_401.status_code = 401

    with patch("backend.soundcloud_service.get_client_id", return_value="fresh_id_fail"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_401, mock_401]):

        with pytest.raises(SoundCloudError) as exc_info:
            get_track_info("https://soundcloud.com/test/track")

        assert "autorisatiefout" in str(exc_info.value).lower() or "401" in str(exc_info.value)


def test_get_download_url_auto_refresh_on_401():
    """Simuleert 401 bij het ophalen van een download-URL en controleert vernieuwing."""
    mock_401 = MagicMock()
    mock_401.status_code = 401

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"url": "https://cf-media.sndcdn.com/final_download.mp3"}

    with patch("backend.soundcloud_service.get_client_id", return_value="fresh_dl_client_id") as mock_get_cid, \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_401, mock_200]):

        dl_url = get_download_url(
            "https://api-v2.soundcloud.com/media/soundcloud:tracks:123/stream",
            client_id="expired_id",
        )
        assert mock_get_cid.call_count == 1
        assert dl_url == "https://cf-media.sndcdn.com/final_download.mp3"


def test_search_tracks_auto_refresh_on_401():
    """Simuleert 401 bij SoundCloud zoeken en verifieert refresh en retry."""
    mock_401 = MagicMock()
    mock_401.status_code = 401

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "collection": [{"id": 1, "title": "Track One"}, {"id": 2, "title": "Track Two"}]
    }

    with patch("backend.soundcloud_service.get_client_id", return_value="fresh_search_id") as mock_get_cid, \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_401, mock_200]):

        results = search_tracks("electronic", client_id="expired_id")
        assert mock_get_cid.call_count == 1
        assert len(results) == 2
        assert results[0]["title"] == "Track One"


def test_get_track_info_hls_stream_parsing():
    """Verifieert dat een HLS-stream correct wordt geselecteerd wanneer er geen progressive is."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "HLS Track",
        "user": {"username": "Artist"},
        "duration": 120000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "hls", "mime_type": 'audio/ogg; codecs="opus"'},
                    "url": "https://api-v2.soundcloud.com/media/opus",
                },
                {
                    "format": {"protocol": "hls", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/hls_mp3",
                },
            ]
        },
    }

    mock_stream_chk = MagicMock()
    mock_stream_chk.status_code = 200
    mock_stream_chk.json.return_value = {"url": "https://cf-media.sndcdn.com/playlist.m3u8"}

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_resolve, mock_stream_chk]):

        info = get_track_info("https://soundcloud.com/test/hls-track")
        assert info["stream_protocol"] == "hls"
        assert info["extension"] == ".mp3"
        assert info["media_type"] == "audio/mpeg"


def test_get_track_info_official_artist_download():
    """Verifieert dat een officiële artist-download voorrang krijgt."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Official DL Track",
        "user": {"username": "Artist"},
        "id": 99999,
        "downloadable": True,
        "has_downloads_left": True,
        "original_format": "flac",
        "media": {"transcodings": []},
    }

    mock_dl_api = MagicMock()
    mock_dl_api.status_code = 200
    mock_dl_api.json.return_value = {"redirectUri": "https://sndcdn.com/download/file.flac"}

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_resolve, mock_dl_api]):

        info = get_track_info("https://soundcloud.com/test/official-dl")
        assert info["is_artist_download"] is True
        assert info["extension"] == ".flac"
        assert info["media_type"] == "audio/flac"
        assert info["direct_url"] == "https://sndcdn.com/download/file.flac"


def test_get_track_info_drm_error():
    """Verifieert dat DRM-beveiligde tracks een SoundCloudDRMError gooien."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "DRM Track",
        "user": {"username": "Major Label"},
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "hls_encrypted", "mime_type": "audio/mp4"},
                    "url": "https://api-v2.soundcloud.com/media/encrypted",
                }
            ]
        },
    }

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", return_value=mock_resolve):

        with pytest.raises(SoundCloudDRMError) as exc_info:
            get_track_info("https://soundcloud.com/test/drm-track")

        assert "DRM-beveiligd" in str(exc_info.value)


def test_stream_audio_progressive():
    """Verifieert dat stream_audio chunks yield voor een progressive MP3."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("backend.soundcloud_service.requests.get", return_value=mock_resp):
        chunks = list(stream_audio("https://cdn.example.com/audio.mp3"))
        assert chunks == [b"chunk1", b"chunk2"]


def test_stream_audio_hls_parallel_ordering():
    """Verifieert dat HLS-segmenten parallel worden opgehaald en in de exacte volgorde worden samengevoegd."""
    playlist_m3u8 = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:10\n"
        "#EXTINF:10.0,\n"
        "https://cf-media.sndcdn.com/seg_0.ts\n"
        "#EXTINF:10.0,\n"
        "https://cf-media.sndcdn.com/seg_1.ts\n"
        "#EXTINF:10.0,\n"
        "https://cf-media.sndcdn.com/seg_2.ts\n"
        "#EXTINF:10.0,\n"
        "https://cf-media.sndcdn.com/seg_3.ts\n"
        "#EXTINF:10.0,\n"
        "https://cf-media.sndcdn.com/seg_4.ts\n"
        "#EXT-X-ENDLIST\n"
    )

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "playlist.m3u8" in url:
            resp.text = playlist_m3u8
        elif "seg_0.ts" in url:
            resp.content = b"segment_0_audio"
        elif "seg_1.ts" in url:
            resp.content = b"segment_1_audio"
        elif "seg_2.ts" in url:
            resp.content = b"segment_2_audio"
        elif "seg_3.ts" in url:
            resp.content = b"segment_3_audio"
        elif "seg_4.ts" in url:
            resp.content = b"segment_4_audio"
        else:
            resp.status_code = 404
            resp.content = b""
        return resp

    with patch("backend.soundcloud_service.requests.get", side_effect=mock_get):
        chunks = list(stream_audio("https://cf-media.sndcdn.com/playlist.m3u8"))

        # Verifieer dat alle segmenten in de exacte volgorde als chunks zijn doorgegeven
        assert chunks == [
            b"segment_0_audio",
            b"segment_1_audio",
            b"segment_2_audio",
            b"segment_3_audio",
            b"segment_4_audio",
        ]
        assert b"".join(chunks) == b"segment_0_audiosegment_1_audiosegment_2_audiosegment_3_audiosegment_4_audio"


def test_stream_audio_hls_with_init_segment():
    """Verifieert dat bij fMP4 HLS het init-segment als eerste wordt gestreamd voor de segmenten."""
    playlist_m3u8 = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4"\n'
        "#EXTINF:10.0,\n"
        "seg_0.m4s\n"
        "#EXTINF:10.0,\n"
        "seg_1.m4s\n"
        "#EXT-X-ENDLIST\n"
    )

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "playlist.m3u8" in url:
            resp.text = playlist_m3u8
        elif "init.mp4" in url:
            resp.iter_content.return_value = [b"init_fmp4_header"]
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = None
        elif "seg_0.m4s" in url:
            resp.content = b"m4a_chunk_0"
        elif "seg_1.m4s" in url:
            resp.content = b"m4a_chunk_1"
        return resp

    with patch("backend.soundcloud_service.requests.get", side_effect=mock_get):
        chunks = list(stream_audio("https://cf-media.sndcdn.com/playlist.m3u8"))
        assert chunks == [b"init_fmp4_header", b"m4a_chunk_0", b"m4a_chunk_1"]
        assert b"".join(chunks) == b"init_fmp4_headerm4a_chunk_0m4a_chunk_1"


def test_stream_audio_hls_worker_network_error():
    """Verifieert dat een netwerkfout in een van de worker-threads wordt afgevangen en omgezet in SoundCloudError."""
    playlist_m3u8 = (
        "#EXTM3U\n"
        "#EXTINF:10.0,\n"
        "seg_0.ts\n"
        "#EXTINF:10.0,\n"
        "seg_1.ts\n"
        "#EXT-X-ENDLIST\n"
    )

    def mock_get(url, *args, **kwargs):
        if "playlist.m3u8" in url:
            resp = MagicMock()
            resp.status_code = 200
            resp.text = playlist_m3u8
            return resp
        elif "seg_1.ts" in url:
            raise requests.RequestException("Connection broken by peer")
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"seg_0_data"
        return resp

    with patch("backend.soundcloud_service.requests.get", side_effect=mock_get):
        with pytest.raises(SoundCloudError) as exc_info:
            list(stream_audio("https://cf-media.sndcdn.com/playlist.m3u8"))
        assert "Netwerkfout tijdens streamen van segment" in str(exc_info.value)
