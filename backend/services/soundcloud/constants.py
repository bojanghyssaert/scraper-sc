"""
Constanten voor SoundCloud scraping, beveiliging en streaming.
"""

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 10

# Toegestane SoundCloud hostnamen voor SSRF-beveiliging
ALLOWED_SOUNDCLOUD_HOSTS = {
    "soundcloud.com",
    "www.soundcloud.com",
    "m.soundcloud.com",
    "on.soundcloud.com",
}

# Toegestane CDN-domeinen voor audiostream SSRF-beveiliging
ALLOWED_CDN_DOMAINS = (
    "soundcloud.com",
    "sndcdn.com",
    "soundcloud.cloud",
    "akamaized.net",
    "cloudfront.net",
)

# Gereserveerde Windows bestandsnamen ter voorkoming van path traversal / OS fouten
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Maximale limieten voor resource-bescherming
MAX_STREAM_SIZE = 250 * 1024 * 1024  # 250 MB
MAX_ZIP_TRACKS = 50
MAX_FILENAME_LENGTH = 120
