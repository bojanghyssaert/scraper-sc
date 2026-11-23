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

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_resolve, mock_stream]):

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

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_resolve, mock_stream]):

        info = get_track_info("https://soundcloud.com/select/track", format_id="m4a")
        assert info["format_id"] == "m4a"
        assert info["extension"] == ".m4a"
        assert info["media_type"] == "audio/mp4"
        assert info["stream_url"] == "https://api-v2.soundcloud.com/media/hls_m4a"
        assert info["filename"].endswith(".m4a")


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

    with patch("backend.soundcloud_service.get_client_id", return_value="dummy_id"), \
         patch("backend.soundcloud_service.requests.get", side_effect=[mock_resolve, mock_stream]):

        with pytest.raises(SoundCloudError) as exc_info:
            get_track_info("https://soundcloud.com/single/track", format_id="ogg")

        assert "Formaat 'ogg' is niet beschikbaar" in str(exc_info.value)


