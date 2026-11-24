"""
SoundCloud service module (backward-compatible facade).

Behoudt volledige achterwaartse compatibiliteit voor main.py en bestaande tests,
terwijl alle logica modulair is opgesplitst in backend/services/soundcloud/.
"""

import sys
import types
import requests

from backend.services.soundcloud import (
    ALLOWED_CDN_DOMAINS,
    ALLOWED_SOUNDCLOUD_HOSTS,
    ERROR_LOG_FILE,
    HEADERS,
    LOGS_DIR,
    MAX_FILENAME_LENGTH,
    MAX_STREAM_SIZE,
    MAX_ZIP_TRACKS,
    PROJECT_ROOT,
    TIMEOUT,
    WINDOWS_RESERVED_NAMES,
    SoundCloudDRMError,
    SoundCloudError,
    convert_m4a_to_mp3,
    download_tracks_as_zip,
    embed_metadata,
    get_cached_client_id,
    get_client_id,
    get_download_url,
    get_track_info,
    logger,
    normalize_audio,
    register_reset_callback,
    register_update_callback,
    reset_client_id,
    sanitize_filename,
    search,
    search_tracks,
    stream_audio,
    validate_cdn_url,
    validate_soundcloud_url,
    _fetch_with_retry,
)
from backend.services.soundcloud import client as _client_mod
from backend.services.soundcloud import downloader as _downloader_mod
from backend.services.soundcloud import media as _media_mod
from backend.services.soundcloud import scraper as _scraper_mod
from backend.services.soundcloud import security as _security_mod

_SUBMODULES = [
    _client_mod,
    _scraper_mod,
    _downloader_mod,
    _media_mod,
    _security_mod,
]


class _SoundCloudServiceModule(types.ModuleType):
    """
    Dynamische facade-module die mutaties (zoals unittest.mock.patch of directe toewijzingen)
    automatisch propageert naar de onderliggende modulaire services.
    """

    @property
    def _cached_client_id(self):
        return _client_mod._cached_client_id

    @_cached_client_id.setter
    def _cached_client_id(self, val):
        _client_mod._cached_client_id = val

    def __setattr__(self, name, val):
        super().__setattr__(name, val)
        if name != "_cached_client_id":
            for submod in _SUBMODULES:
                if hasattr(submod, name):
                    setattr(submod, name, val)


sys.modules[__name__].__class__ = _SoundCloudServiceModule

__all__ = [
    "HEADERS",
    "TIMEOUT",
    "ALLOWED_SOUNDCLOUD_HOSTS",
    "ALLOWED_CDN_DOMAINS",
    "WINDOWS_RESERVED_NAMES",
    "MAX_STREAM_SIZE",
    "MAX_ZIP_TRACKS",
    "MAX_FILENAME_LENGTH",
    "validate_soundcloud_url",
    "validate_cdn_url",
    "sanitize_filename",
    "PROJECT_ROOT",
    "LOGS_DIR",
    "ERROR_LOG_FILE",
    "logger",
    "SoundCloudError",
    "SoundCloudDRMError",
    "_cached_client_id",
    "register_reset_callback",
    "register_update_callback",
    "reset_client_id",
    "get_cached_client_id",
    "get_client_id",
    "_fetch_with_retry",
    "get_track_info",
    "search_tracks",
    "search",
    "get_download_url",
    "stream_audio",
    "download_tracks_as_zip",
    "embed_metadata",
    "normalize_audio",
    "convert_m4a_to_mp3",
    "requests",
]
