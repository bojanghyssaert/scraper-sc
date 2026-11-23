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
    embed_metadata,
    convert_m4a_to_mp3,
    download_tracks_as_zip,
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


def test_search_tracks_drm_detection_and_fields():
    """Verifieert dat search_tracks metadata formatteert en DRM-status correct berekent."""
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "collection": [
            {
                "id": 101,
                "title": "Unencrypted Track",
                "user": {"username": "Artist One"},
                "artwork_url": "https://i1.sndcdn.com/artworks-large.jpg",
                "duration": 180000,
                "permalink_url": "https://soundcloud.com/artist-one/unencrypted",
                "downloadable": False,
                "media": {
                    "transcodings": [
                        {
                            "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                            "url": "https://api-v2.soundcloud.com/media/prog",
                        }
                    ]
                },
            },
            {
                "id": 102,
                "title": "DRM Track",
                "user": {"username": "Artist Two"},
                "artwork_url": "https://i1.sndcdn.com/artworks-drm-large.jpg",
                "duration": 240000,
                "permalink_url": "https://soundcloud.com/artist-two/drm-track",
                "downloadable": False,
                "media": {
                    "transcodings": [
                        {
                            "format": {"protocol": "hls/encrypted", "mime_type": "audio/mpegurl"},
                            "url": "https://api-v2.soundcloud.com/media/enc",
                        }
                    ]
                },
            },
            {
                "id": 103,
                "title": "Artist Download Track",
                "publisher_metadata": {"artist": "Special Artist"},
                "artwork_url": None,
                "duration": 120000,
                "permalink_url": "https://soundcloud.com/special-artist/downloadable",
                "downloadable": True,
                "has_downloads_left": True,
                "media": {"transcodings": []},
            },
        ]
    }

    with patch("backend.soundcloud_service.requests.get", return_value=mock_200):
        results = search_tracks("test query", client_id="test_cid", limit=8)

        assert len(results) == 3

        # Track 1: onbeveiligde stream -> is_drm = False
        assert results[0]["title"] == "Unencrypted Track"
        assert results[0]["artist"] == "Artist One"
        assert results[0]["artwork_url"] == "https://i1.sndcdn.com/artworks-t500x500.jpg"
        assert results[0]["duration_ms"] == 180000
        assert results[0]["permalink_url"] == "https://soundcloud.com/artist-one/unencrypted"
        assert results[0]["is_drm"] is False

        # Track 2: alleen encrypted stream, geen download -> is_drm = True
        assert results[1]["title"] == "DRM Track"
        assert results[1]["artist"] == "Artist Two"
        assert results[1]["is_drm"] is True

        # Track 3: officiële artist download aanwezig -> is_drm = False
        assert results[2]["title"] == "Artist Download Track"
        assert results[2]["artist"] == "Special Artist"
        assert results[2]["artwork_url"] == ""
        assert results[2]["is_drm"] is False


def test_search_tracks_null_publisher_metadata_and_user():
    """Verifieert dat search_tracks niet crasht wanneer publisher_metadata of user None/null is in de response."""
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "collection": [
            {
                "id": 999,
                "title": "Null Metadata Track",
                "publisher_metadata": None,
                "user": None,
                "artwork_url": None,
                "duration": 210000,
                "permalink_url": "https://soundcloud.com/test/null-track",
                "downloadable": False,
                "media": None,
            },
            {
                "id": 1000,
                "title": "Null Transcodings Track",
                "publisher_metadata": None,
                "user": {"username": "Fallback User"},
                "media": {"transcodings": None},
            },
        ]
    }

    with patch("backend.soundcloud_service.requests.get", return_value=mock_200):
        results = search_tracks("null query", client_id="test_cid", limit=8)
        assert len(results) == 2
        assert results[0]["title"] == "Null Metadata Track"
        assert results[0]["artist"] == "Onbekende artiest"
        assert results[0]["is_drm"] is True
        assert results[1]["title"] == "Null Transcodings Track"
        assert results[1]["artist"] == "Fallback User"


def test_search_tracks_empty_query():
    """Verifieert dat een lege zoekopdracht direct een lege lijst teruggeeft zonder netwerkverzoek."""
    assert search_tracks("", client_id="cid") == []
    assert search_tracks("   ", client_id="cid") == []


def test_search_tracks_api_error():
    """Verifieert dat search_tracks een SoundCloudError opwerpt bij een HTTP-foutcode of ongeldig JSON."""
    mock_500 = MagicMock()
    mock_500.status_code = 500

    with patch("backend.soundcloud_service.requests.get", return_value=mock_500):
        with pytest.raises(SoundCloudError, match="SoundCloud zoek-API gaf foutcode 500 terug"):
            search_tracks("fail", client_id="cid")


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


def test_embed_metadata_mp3_with_artwork():
    """Verifieert dat ID3 tags (TIT2, TPE1, APIC) correct worden toegevoegd aan MP3."""
    import io
    from mutagen.id3 import ID3

    raw_audio = b"FAKE_MP3_STREAM_CONTENT_12345"
    info = {
        "title": "Zomerbries",
        "artist": "De Artiest",
        "artwork_url": "https://i1.sndcdn.com/artworks-sample-t500x500.jpg",
    }
    fake_artwork = b"\xff\xd8\xff\xe0" + b"\x00" * 20

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_artwork

    with patch("backend.soundcloud_service.requests.get", return_value=mock_resp) as mock_get:
        tagged_bytes = embed_metadata(raw_audio, ".mp3", info)
        assert tagged_bytes != raw_audio
        assert tagged_bytes.endswith(raw_audio)
        assert mock_get.call_count == 1

        tags = ID3(io.BytesIO(tagged_bytes))
        assert str(tags.get("TIT2")) == "Zomerbries"
        assert str(tags.get("TPE1")) == "De Artiest"
        apic_frames = tags.getall("APIC")
        assert len(apic_frames) == 1
        assert apic_frames[0].mime == "image/jpeg"
        assert apic_frames[0].data == fake_artwork


def test_embed_metadata_mp3_with_png_artwork():
    """Verifieert dat PNG artwork wordt herkend en als image/png wordt getagd."""
    import io
    from mutagen.id3 import ID3

    raw_audio = b"FAKE_MP3_PNG"
    info = {
        "title": "PNG Track",
        "artist": "PNG Artist",
        "artwork_url": "https://i1.sndcdn.com/artworks-png.png",
    }
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_png

    with patch("backend.soundcloud_service.requests.get", return_value=mock_resp):
        tagged = embed_metadata(raw_audio, "mp3", info)
        tags = ID3(io.BytesIO(tagged))
        apic = tags.getall("APIC")[0]
        assert apic.mime == "image/png"
        assert apic.data == fake_png


def test_embed_metadata_mp3_artwork_download_fails_safe():
    """
    Verifieert dat een mislukte cover-download (bijv. timeout of netwerkfout)
    de audiodownload en het taggen van titel/artiest niet blokkeert.
    """
    import io
    from mutagen.id3 import ID3

    raw_audio = b"SAFE_AUDIO_STREAM_CONTENT"
    info = {
        "title": "Robuuste Track",
        "artist": "Robuuste Artiest",
        "artwork_url": "https://i1.sndcdn.com/artworks-broken.jpg",
    }

    with patch("backend.soundcloud_service.requests.get", side_effect=requests.RequestException("Connection timeout")):
        tagged_bytes = embed_metadata(raw_audio, ".mp3", info)
        assert tagged_bytes.endswith(raw_audio)

        tags = ID3(io.BytesIO(tagged_bytes))
        assert str(tags.get("TIT2")) == "Robuuste Track"
        assert str(tags.get("TPE1")) == "Robuuste Artiest"
        assert len(tags.getall("APIC")) == 0


def test_embed_metadata_m4a_with_artwork():
    """Verifieert dat MP4 tags (\xa9nam, \xa9ART, covr) correct worden toegevoegd aan .m4a."""
    import struct
    import io
    from mutagen.mp4 import MP4, Atom

    ftyp = Atom.render(b"ftyp", b"M4A \x00\x00\x00\x00M4A mp42isom")
    mvhd_body = b"\x00\x00\x00\x00" + struct.pack(">LLLL", 0, 0, 1000, 1000) + b"\x00" * 80
    mvhd = Atom.render(b"mvhd", mvhd_body)
    udta = Atom.render(b"udta", b"")
    moov = Atom.render(b"moov", mvhd + udta)
    raw_m4a = ftyp + moov

    info = {
        "title": "M4A Track",
        "artist": "M4A Artist",
        "artwork_url": "https://i1.sndcdn.com/artworks-m4a.jpg",
    }
    fake_artwork = b"\xff\xd8\xff\xe0" + b"\x00" * 30

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_artwork

    with patch("backend.soundcloud_service.requests.get", return_value=mock_resp):
        tagged_bytes = embed_metadata(raw_m4a, ".m4a", info)
        assert tagged_bytes != raw_m4a

        audio = MP4(fileobj=io.BytesIO(tagged_bytes))
        assert audio["\xa9nam"] == ["M4A Track"]
        assert audio["\xa9ART"] == ["M4A Artist"]
        assert len(audio["covr"]) == 1
        assert bytes(audio["covr"][0]) == fake_artwork


def test_embed_metadata_m4a_artwork_download_fails_safe():
    """Verifieert dat MP4 tagging faal-veilig is bij een mislukte artwork download."""
    import struct
    import io
    from mutagen.mp4 import MP4, Atom

    ftyp = Atom.render(b"ftyp", b"M4A \x00\x00\x00\x00M4A mp42isom")
    mvhd_body = b"\x00\x00\x00\x00" + struct.pack(">LLLL", 0, 0, 1000, 1000) + b"\x00" * 80
    mvhd = Atom.render(b"mvhd", mvhd_body)
    udta = Atom.render(b"udta", b"")
    moov = Atom.render(b"moov", mvhd + udta)
    raw_m4a = ftyp + moov

    info = {
        "title": "M4A Safe Track",
        "artist": "M4A Safe Artist",
        "artwork_url": "https://i1.sndcdn.com/artworks-fail.jpg",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.content = b"Internal Server Error"

    with patch("backend.soundcloud_service.requests.get", return_value=mock_resp):
        tagged_bytes = embed_metadata(raw_m4a, ".m4a", info)
        audio = MP4(fileobj=io.BytesIO(tagged_bytes))
        assert audio["\xa9nam"] == ["M4A Safe Track"]
        assert audio["\xa9ART"] == ["M4A Safe Artist"]
        assert "covr" not in audio


def test_embed_metadata_unsupported_or_empty_returns_original():
    """Verifieert dat onbekende extensies, lege data of corrupties veilig de originele bytes teruggeven."""
    assert embed_metadata(b"", ".mp3", {}) == b""

    wav_data = b"RIFF1234WAVEfmt "
    assert embed_metadata(wav_data, ".wav", {"title": "WAV Track"}) == wav_data

    corrupt_mp4 = b"not a valid mp4 file at all"
    assert embed_metadata(corrupt_mp4, ".m4a", {"title": "Corrupt"}) == corrupt_mp4


def test_get_track_info_returns_available_formats():
    """Verifieert dat get_track_info een lijst formats teruggeeft met MP3 en M4A opties."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Dual Format Track",
        "user": {"username": "Dual Artist"},
        "duration": 180000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/prog_mp3",
                },
                {
                    "format": {"protocol": "hls", "mime_type": 'audio/mp4; codecs="mp4a.40.2"'},
                    "url": "https://api-v2.soundcloud.com/media/hls_m4a",
                },
            ]
        },
    }

    mock_stream = MagicMock()
    mock_stream.status_code = 200
    mock_stream.json.return_value = {"url": "https://cf-media.sndcdn.com/prog.mp3"}

    mock_m4a = MagicMock()
    mock_m4a.status_code = 200
    mock_m4a.json.return_value = {"url": "https://cf-media.sndcdn.com/stream.m3u8"}

    def mock_get(url, *args, **kwargs):
        if "prog_mp3" in url:
            return mock_stream
        if "hls_m4a" in url:
            return mock_m4a
        return mock_resolve

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=mock_get):

        info = get_track_info("https://soundcloud.com/dual/track")
        assert "formats" in info
        assert len(info["formats"]) == 2
        format_ids = [f["id"] for f in info["formats"]]
        assert "mp3" in format_ids
        assert "m4a" in format_ids

        # Standaard gekozen formaat is MP3
        assert info["format_id"] == "mp3"
        assert info["extension"] == ".mp3"
        assert info["media_type"] == "audio/mpeg"


def test_get_track_info_select_m4a_format():
    """Verifieert dat bij format_id='m4a' het M4A-formaat wordt geselecteerd."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Select M4A Track",
        "user": {"username": "Select Artist"},
        "duration": 120000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/prog_mp3",
                },
                {
                    "format": {"protocol": "hls", "mime_type": "audio/mp4"},
                    "url": "https://api-v2.soundcloud.com/media/hls_m4a",
                },
            ]
        },
    }

    mock_stream = MagicMock()
    mock_stream.status_code = 200
    mock_stream.json.return_value = {"url": "https://cf-media.sndcdn.com/prog.mp3"}

    mock_m4a = MagicMock()
    mock_m4a.status_code = 200
    mock_m4a.json.return_value = {"url": "https://cf-media.sndcdn.com/stream.m3u8"}

    def mock_get(url, *args, **kwargs):
        if "prog_mp3" in url:
            return mock_stream
        if "hls_m4a" in url:
            return mock_m4a
        return mock_resolve

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=mock_get):

        info = get_track_info("https://soundcloud.com/select/track", format_id="m4a")
        assert info["format_id"] == "m4a"
        assert info["extension"] == ".mp3"
        assert info["media_type"] == "audio/mpeg"
        assert info["stream_url"] == "https://api-v2.soundcloud.com/media/hls_m4a"
        assert info["filename"].endswith(".mp3")
        assert info["is_m4a"] is True


def test_get_track_info_only_m4a_stream():
    """Verifieert dat wanneer een track alleen een M4A-stream heeft, deze automatisch als MP3 wordt aangeboden."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Solo M4A Track",
        "user": {"username": "Solo Artist"},
        "duration": 150000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "hls", "mime_type": "audio/mp4"},
                    "url": "https://api-v2.soundcloud.com/media/hls_m4a",
                },
            ]
        },
    }
    mock_stream = MagicMock()
    mock_stream.status_code = 200
    mock_stream.json.return_value = {"url": "https://cf-media.sndcdn.com/playlist.m3u8"}

    def mock_get(url, *args, **kwargs):
        if "hls_m4a" in url:
            return mock_stream
        return mock_resolve

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=mock_get):

        info = get_track_info("https://soundcloud.com/solo/m4a-track")
        assert info["format_id"] == "m4a"
        assert info["extension"] == ".mp3"
        assert info["media_type"] == "audio/mpeg"
        assert info["filename"] == "Solo Artist - Solo M4A Track.mp3"
        assert info["is_m4a"] is True
        assert len(info["formats"]) == 1
        assert info["formats"][0]["label"] == "MP3 (via M4A)"
        assert info["formats"][0]["extension"] == ".mp3"


def test_get_track_info_mp3_fails_and_m4a_succeeds():
    """
    Verifieert dat wanneer de MP3-transcoding een HTTP 400/404 fout geeft
    en de M4A-transcoding wel geldig is, alleen M4A in 'formats' wordt opgenomen.
    """
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Broken MP3 Track",
        "user": {"username": "Electro Producer"},
        "duration": 200000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/broken_mp3",
                },
                {
                    "format": {"protocol": "hls", "mime_type": "audio/mp4"},
                    "url": "https://api-v2.soundcloud.com/media/working_m4a",
                },
            ]
        },
    }

    mock_400_mp3 = MagicMock()
    mock_400_mp3.status_code = 400

    mock_200_m4a = MagicMock()
    mock_200_m4a.status_code = 200
    mock_200_m4a.json.return_value = {"url": "https://cf-media.sndcdn.com/playlist.m3u8"}

    def mock_get(url, *args, **kwargs):
        if "broken_mp3" in url:
            return mock_400_mp3
        if "working_m4a" in url:
            return mock_200_m4a
        return mock_resolve

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=mock_get):

        info = get_track_info("https://soundcloud.com/artist/broken-mp3-track")

        assert len(info["formats"]) == 1
        assert info["formats"][0]["id"] == "m4a"
        assert info["formats"][0]["label"] == "MP3 (via M4A)"
        assert info["formats"][0]["extension"] == ".mp3"
        format_ids = [f["id"] for f in info["formats"]]
        assert "mp3" not in format_ids
        assert info["format_id"] == "m4a"
        assert info["extension"] == ".mp3"
        assert info["media_type"] == "audio/mpeg"
        assert info["stream_url"] == "https://api-v2.soundcloud.com/media/working_m4a"
        assert info["stream_protocol"] == "hls"
        assert info["is_m4a"] is True
        assert info["filename"].endswith(".mp3")


def test_get_track_info_all_transcodings_fail_raises_soundcloud_error():
    """
    Verifieert dat wanneer alle niet-DRM transcodings falen en de track niet downloadable is,
    een duidelijke SoundCloudError wordt opgegooid.
    """
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "All Streams Broken Track",
        "user": {"username": "Broken Artist"},
        "duration": 150000,
        "downloadable": False,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/broken_mp3",
                },
                {
                    "format": {"protocol": "hls", "mime_type": "audio/mp4"},
                    "url": "https://api-v2.soundcloud.com/media/broken_m4a",
                },
            ]
        },
    }

    mock_404 = MagicMock()
    mock_404.status_code = 404

    def mock_get(url, *args, **kwargs):
        if "media/broken_" in url:
            return mock_404
        return mock_resolve

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=mock_get):

        with pytest.raises(SoundCloudError) as exc_info:
            get_track_info("https://soundcloud.com/artist/all-broken-track")

        assert "Geen ondersteunde onbeveiligde MP3- of M4A-stream gevonden" in str(exc_info.value)


def test_get_track_info_official_download_with_formats():
    """Verifieert dat bij een downloadable track zowel 'original' als streams in formats zitten."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Multi Option DL",
        "user": {"username": "Pro Artist"},
        "id": 8888,
        "downloadable": True,
        "has_downloads_left": True,
        "original_format": "wav",
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/prog_mp3",
                }
            ]
        },
    }

    mock_dl_api = MagicMock()
    mock_dl_api.status_code = 200
    mock_dl_api.json.return_value = {"redirectUri": "https://sndcdn.com/download/file.wav"}

    mock_stream = MagicMock()
    mock_stream.status_code = 200
    mock_stream.json.return_value = {"url": "https://cf-media.sndcdn.com/prog.mp3"}

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_resolve, mock_dl_api, mock_stream]):

        # Zonder format_id is original de standaard
        info = get_track_info("https://soundcloud.com/pro/dl")
        assert info["format_id"] == "original"
        assert info["extension"] == ".wav"
        assert info["is_artist_download"] is True

        format_ids = [f["id"] for f in info["formats"]]
        assert "original" in format_ids
        assert "mp3" in format_ids
        orig_fmt = next(f for f in info["formats"] if f["id"] == "original")
        assert orig_fmt["label"] == "Origineel bestand (WAV)"


def test_get_track_info_invalid_format_id_raises():
    """Verifieert dat een niet-beschikbaar format_id een SoundCloudError oplevert."""
    mock_resolve = MagicMock()
    mock_resolve.status_code = 200
    mock_resolve.json.return_value = {
        "title": "Single Format",
        "user": {"username": "Artist"},
        "duration": 60000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/prog_mp3",
                }
            ]
        },
    }

    mock_stream = MagicMock()
    mock_stream.status_code = 200
    mock_stream.json.return_value = {"url": "https://cf-media.sndcdn.com/prog.mp3"}

    mock_m4a = MagicMock()
    mock_m4a.status_code = 200
    mock_m4a.json.return_value = {"url": "https://cf-media.sndcdn.com/stream.m3u8"}

    def mock_get(url, *args, **kwargs):
        if "prog_mp3" in url:
            return mock_stream
        if "hls_m4a" in url:
            return mock_m4a
        return mock_resolve

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=mock_get):

        with pytest.raises(SoundCloudError) as exc_info:
            get_track_info("https://soundcloud.com/single/track", format_id="ogg")

        assert "Formaat 'ogg' is niet beschikbaar" in str(exc_info.value)


def test_get_track_info_playlist_with_stubs():
    """Verifieert dat een playlist correct wordt ontleed inclusief ontbrekende stub-tracks via /tracks?ids=..."""
    mock_playlist_resp = MagicMock()
    mock_playlist_resp.status_code = 200
    mock_playlist_resp.json.return_value = {
        "kind": "playlist",
        "title": "Summer Vibes Set",
        "user": {"username": "DJ Chill"},
        "artwork_url": "https://i1.sndcdn.com/artworks-playlist-large.jpg",
        "tracks": [
            {
                "id": 101,
                "title": "First Full Track",
                "user": {"username": "DJ Chill"},
                "permalink_url": "https://soundcloud.com/dj-chill/first-track",
                "duration": 180000,
                "downloadable": False,
                "media": {
                    "transcodings": [
                        {
                            "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                            "url": "https://api-v2.soundcloud.com/media/prog1",
                        }
                    ]
                },
            },
            {
                "id": 202,
                # Stub track: ontbreekt title en media
            },
        ],
    }

    mock_tracks_batch_resp = MagicMock()
    mock_tracks_batch_resp.status_code = 200
    mock_tracks_batch_resp.json.return_value = [
        {
            "id": 202,
            "title": "Second Resolved Track",
            "user": {"username": "Guest Producer"},
            "permalink_url": "https://soundcloud.com/guest/second-track",
            "duration": 210000,
            "downloadable": True,
            "has_downloads_left": True,
            "media": {
                "transcodings": [
                    {
                        "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                        "url": "https://api-v2.soundcloud.com/media/prog2",
                    }
                ]
            },
        }
    ]

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_cid"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_playlist_resp, mock_tracks_batch_resp]):

        info = get_track_info("https://soundcloud.com/dj-chill/sets/summer-vibes")

        assert info["type"] == "playlist"
        assert info["title"] == "Summer Vibes Set"
        assert info["artist"] == "DJ Chill"
        assert info["artwork_url"] == "https://i1.sndcdn.com/artworks-playlist-t500x500.jpg"
        assert len(info["tracks"]) == 2

        t1 = info["tracks"][0]
        assert t1["title"] == "First Full Track"
        assert t1["artist"] == "DJ Chill"
        assert t1["duration_ms"] == 180000
        assert t1["url"] == "https://soundcloud.com/dj-chill/first-track"
        assert t1["is_drm"] is False
        assert t1["downloadable"] is True

        t2 = info["tracks"][1]
        assert t2["title"] == "Second Resolved Track"
        assert t2["artist"] == "Guest Producer"
        assert t2["url"] == "https://soundcloud.com/guest/second-track"
        assert t2["is_drm"] is False
        assert t2["downloadable"] is True


def test_get_track_info_null_publisher_metadata_and_user():
    """Verifieert dat get_track_info niet crasht wanneer publisher_metadata of user None/null is in de response."""
    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {
        "id": 888,
        "title": "Track With Nulls",
        "publisher_metadata": None,
        "user": None,
        "artwork_url": None,
        "duration": 180000,
        "media": {
            "transcodings": [
                {
                    "format": {"protocol": "progressive", "mime_type": "audio/mpeg"},
                    "url": "https://api-v2.soundcloud.com/media/stream_prog",
                }
            ]
        },
        "url": "https://cf-media.sndcdn.com/stream.mp3",
    }

    with patch("backend.soundcloud_service._fetch_with_retry", return_value=(mock_200, "cid_123")):
        info = get_track_info("https://soundcloud.com/test/null-track", client_id="cid_123")
        assert info["title"] == "Track With Nulls"
        assert info["artist"] == "Onbekende artiest"
        assert info["filename"] == "Onbekende artiest - Track With Nulls.mp3"


def test_download_tracks_as_zip_success():
    """Verifieert dat download_tracks_as_zip audiobestanden downloadt en bundelt in een geldig ZIP-bestand."""
    import zipfile
    import io

    mock_track_info_1 = {
        "title": "Track One",
        "artist": "Artist One",
        "filename": "Artist One - Track One.mp3",
        "extension": ".mp3",
        "stream_url": "https://api-v2.soundcloud.com/media/s1",
        "stream_protocol": "progressive",
    }
    mock_track_info_2 = {
        "title": "Track Two",
        "artist": "Artist Two",
        "filename": "Artist Two - Track Two.mp3",
        "extension": ".mp3",
        "stream_url": "https://api-v2.soundcloud.com/media/s2",
        "stream_protocol": "progressive",
    }

    with patch("backend.soundcloud_service.get_track_info", side_effect=[mock_track_info_1, mock_track_info_2]), \
         patch("backend.soundcloud_service.get_download_url", side_effect=["https://cdn.com/1.mp3", "https://cdn.com/2.mp3"]), \
         patch("backend.soundcloud_service.stream_audio", side_effect=[iter([b"audio_one"]), iter([b"audio_two"])]), \
         patch("backend.soundcloud_service.embed_metadata", side_effect=lambda audio, ext, info: audio):

        zip_data = download_tracks_as_zip(
            ["https://soundcloud.com/a/1", "https://soundcloud.com/a/2"],
            client_id="dummy_cid",
        )

        assert isinstance(zip_data, bytes)
        assert len(zip_data) > 0

        # Verifieer inhoud van het ZIP-archief
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            namelist = zf.namelist()
            assert "Artist One - Track One.mp3" in namelist
            assert "Artist Two - Track Two.mp3" in namelist
            assert zf.read("Artist One - Track One.mp3") == b"audio_one"
            assert zf.read("Artist Two - Track Two.mp3") == b"audio_two"


def test_download_tracks_as_zip_empty():
    """Verifieert dat een lege lijst van track_urls een SoundCloudError opwerpt."""
    with pytest.raises(SoundCloudError, match="Geen tracks opgegeven"):
        download_tracks_as_zip([])


def test_convert_m4a_to_mp3_empty_input():
    """Verifieert dat een lege byte-string direct een SoundCloudError oplevert."""
    with pytest.raises(SoundCloudError, match="Geen audiogegevens ontvangen"):
        convert_m4a_to_mp3(b"")


def test_convert_m4a_to_mp3_ffmpeg_not_found():
    """Verifieert dat ontbreken van FFmpeg een SoundCloudError oplevert."""
    with patch("shutil.which", return_value=None), \
         patch("imageio_ffmpeg.get_ffmpeg_exe", return_value=None):
        with pytest.raises(SoundCloudError, match="FFmpeg executable niet gevonden"):
            convert_m4a_to_mp3(b"dummy_m4a_bytes")


def test_convert_m4a_to_mp3_called_process_error():
    """Verifieert dat een fout in het FFmpeg-proces netjes wordt opgevangen in een SoundCloudError."""
    import subprocess
    err = subprocess.CalledProcessError(
        returncode=1,
        cmd=["ffmpeg"],
        stderr=b"Invalid data found when processing input",
    )
    with patch("shutil.which", return_value="ffmpeg"), \
         patch("subprocess.run", side_effect=err):
        with pytest.raises(SoundCloudError) as exc_info:
            convert_m4a_to_mp3(b"corrupt_m4a_data")
        assert "Invalid data found when processing input" in str(exc_info.value)


def test_convert_m4a_to_mp3_missing_output():
    """Verifieert dat wanneer output.mp3 niet gegenereerd is, een SoundCloudError optreedt."""
    with patch("shutil.which", return_value="ffmpeg"), \
         patch("subprocess.run") as mock_run:
        # subprocess.run slaagt, maar maakt geen output.mp3 aan
        with pytest.raises(SoundCloudError, match="FFmpeg heeft geen output.mp3 bestand gegenereerd"):
            convert_m4a_to_mp3(b"dummy_m4a_data")


def test_convert_m4a_to_mp3_mocked_success():
    """Verifieert een succesvolle conversie via gemockte subprocess.run en controleert opruiming van tijdelijke bestanden."""
    from pathlib import Path
    temp_dirs_created = []

    def fake_subprocess_run(cmd, check, capture_output):
        out_path = Path(cmd[-1])
        temp_dirs_created.append(out_path.parent)
        out_path.write_bytes(b"\xff\xfb\x90\x64" + b"mocked_mp3_data")
        return MagicMock(returncode=0)

    with patch("shutil.which", return_value="ffmpeg"), \
         patch("subprocess.run", side_effect=fake_subprocess_run):
        result = convert_m4a_to_mp3(b"input_m4a_bytes")
        assert result.startswith(b"\xff\xfb\x90\x64")
        assert b"mocked_mp3_data" in result

    # Controleer dat de tijdelijke directory na afloop niet meer bestaat
    for d in temp_dirs_created:
        assert not d.exists()


def test_convert_m4a_to_mp3_real_ffmpeg_and_embed_metadata():
    """Verifieert echte conversie via imageio-ffmpeg en controleert dat ID3-tags correct worden toegevoegd."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    import imageio_ffmpeg
    from mutagen.id3 import ID3

    ffmpeg_exe = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
    assert ffmpeg_exe is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        test_m4a_path = Path(tmpdir) / "test.m4a"
        # Genereer 0.5s audio sine wave als M4A/AAC
        subprocess.run(
            [ffmpeg_exe, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", "-c:a", "aac", str(test_m4a_path)],
            check=True,
            capture_output=True,
        )
        raw_m4a_bytes = test_m4a_path.read_bytes()

    # Converteer naar MP3
    mp3_bytes = convert_m4a_to_mp3(raw_m4a_bytes)
    assert len(mp3_bytes) > 0

    # Voeg ID3 metadata toe
    track_info = {
        "title": "Real Converted Track",
        "artist": "Real Converted Artist",
        "artwork_url": "",
    }
    tagged_mp3 = embed_metadata(mp3_bytes, ".mp3", track_info)

    # Lees tags uit met Mutagen
    import io
    tags = ID3(io.BytesIO(tagged_mp3))
    assert str(tags.get("TIT2")) == "Real Converted Track"
    assert str(tags.get("TPE1")) == "Real Converted Artist"


def test_download_tracks_as_zip_converts_m4a():
    """Verifieert dat download_tracks_as_zip M4A-tracks converteert naar MP3 en van ID3-tags voorziet."""
    import zipfile
    import io
    from mutagen.id3 import ID3

    mock_m4a_info = {
        "type": "track",
        "title": "M4A Zip Track",
        "artist": "M4A Zip Artist",
        "filename": "M4A Zip Artist - M4A Zip Track.mp3",
        "extension": ".mp3",
        "media_type": "audio/mpeg",
        "stream_url": "https://api-v2.soundcloud.com/media/hls_m4a",
        "stream_protocol": "hls",
        "is_m4a": True,
        "format_id": "m4a",
    }

    dummy_mp3_base = b"\xff\xfb\x90\x64" + b"\x00" * 400

    with patch("backend.soundcloud_service.get_track_info", return_value=mock_m4a_info), \
         patch("backend.soundcloud_service.get_download_url", return_value="https://cdn.com/playlist.m3u8"), \
         patch("backend.soundcloud_service.stream_audio", return_value=iter([b"m4a_zip_audio"])), \
         patch("backend.soundcloud_service.convert_m4a_to_mp3", return_value=dummy_mp3_base) as mock_convert:

        zip_data = download_tracks_as_zip(["https://soundcloud.com/artist/m4a-zip-track"], client_id="test_cid")
        assert len(zip_data) > 0
        mock_convert.assert_called_once_with(b"m4a_zip_audio")

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            assert "M4A Zip Artist - M4A Zip Track.mp3" in zf.namelist()
            file_bytes = zf.read("M4A Zip Artist - M4A Zip Track.mp3")
            tags = ID3(io.BytesIO(file_bytes))
            assert str(tags.get("TIT2")) == "M4A Zip Track"
            assert str(tags.get("TPE1")) == "M4A Zip Artist"


