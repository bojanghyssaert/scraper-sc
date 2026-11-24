"""
SoundCloud service package.

Biedt alle functionaliteiten voor het ophalen van de client_id,
zoeken, track- en playlist-metadata parsen, audio streamen en converteren.
"""

from .constants import (
    ALLOWED_CDN_DOMAINS,
    ALLOWED_SOUNDCLOUD_HOSTS,
    HEADERS,
    MAX_FILENAME_LENGTH,
    MAX_STREAM_SIZE,
    MAX_ZIP_TRACKS,
    TIMEOUT,
    WINDOWS_RESERVED_NAMES,
)
from .exceptions import SoundCloudDRMError, SoundCloudError
from .logging_config import ERROR_LOG_FILE, LOGS_DIR, PROJECT_ROOT, logger
from .security import (
    sanitize_filename,
    validate_cdn_url,
    validate_soundcloud_url,
)
from .client import (
    _cached_client_id,
    _fetch_with_retry,
    get_cached_client_id,
    get_client_id,
    register_reset_callback,
    register_update_callback,
    reset_client_id,
)
from .media import (
    convert_m4a_to_mp3,
    embed_metadata,
    normalize_audio,
)
from .downloader import (
    download_tracks_as_zip,
    get_download_url,
    stream_audio,
)
from .scraper import (
    get_track_info,
    search,
    search_tracks,
)

__all__ = [
    # Constanten & Beveiliging
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
    # Logging & Uitzonderingen
    "PROJECT_ROOT",
    "LOGS_DIR",
    "ERROR_LOG_FILE",
    "logger",
    "SoundCloudError",
    "SoundCloudDRMError",
    # Client & Autorisatie
    "_cached_client_id",
    "register_reset_callback",
    "register_update_callback",
    "reset_client_id",
    "get_cached_client_id",
    "get_client_id",
    "_fetch_with_retry",
    # Scraping & Zoeken
    "get_track_info",
    "search_tracks",
    "search",
    # Streaming & Download
    "get_download_url",
    "stream_audio",
    "download_tracks_as_zip",
    # Audioverwerking
    "embed_metadata",
    "normalize_audio",
    "convert_m4a_to_mp3",
]
