"""
Beveiligings- en validatiefuncties voor SoundCloud URLs en bestandsnamen.
"""

import ipaddress
import re
import urllib.parse

from .constants import (
    ALLOWED_CDN_DOMAINS,
    ALLOWED_SOUNDCLOUD_HOSTS,
    MAX_FILENAME_LENGTH,
    WINDOWS_RESERVED_NAMES,
)
from .exceptions import SoundCloudError


def validate_soundcloud_url(url: str) -> str:
    """
    Valideert of een opgegeven URL een legitieme SoundCloud-URL is via HTTPS.
    Blokkeert onveilige schema's (zoals http:// of file://), IP-adressen, localhost en vreemde domeinen (SSRF-beveiliging).

    Args:
        url: De te valideren URL string.

    Returns:
        De genormaliseerde, opgeschoonde URL string.

    Raises:
        SoundCloudError: Als de URL ongeldig, onveilig of niet van SoundCloud is.
    """
    if not url or not isinstance(url, str):
        raise SoundCloudError("Geen geldige SoundCloud-URL opgegeven.")

    trimmed = url.strip()
    if not trimmed:
        raise SoundCloudError("Geen geldige SoundCloud-URL opgegeven.")

    try:
        parsed = urllib.parse.urlparse(trimmed)
    except Exception as exc:
        raise SoundCloudError(f"Ongeldige URL-syntaxis: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise SoundCloudError(
            f"Onveilig URL-schema '{parsed.scheme}://'. Alleen beveiligde 'https://' SoundCloud-links zijn toegestaan."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname not in ALLOWED_SOUNDCLOUD_HOSTS:
        raise SoundCloudError(
            f"Ongeldig SoundCloud-domein '{hostname}'. Alleen officiële SoundCloud-links zijn toegestaan "
            f"({', '.join(sorted(ALLOWED_SOUNDCLOUD_HOSTS))})."
        )

    if not parsed.path or parsed.path.strip("/") == "":
        raise SoundCloudError("Ongeldige SoundCloud-URL: er is geen track- of playlist-pad opgegeven.")

    return trimmed


def validate_cdn_url(url: str) -> str:
    """
    Valideert of een stream- of CDN-link afkomstig is van een geautoriseerd SoundCloud CDN-domein
    (*.soundcloud.com, *.sndcdn.com, *.soundcloud.cloud, *.akamaized.net, *.cloudfront.net)
    ter voorkoming van SSRF-aanvallen via audio-streams.

    Args:
        url: De stream- of CDN-URL.

    Returns:
        De gevalideerde URL string.

    Raises:
        SoundCloudError: Als het URL-schema niet HTTPS is of het doeldomein niet geautoriseerd is.
    """
    if not url or not isinstance(url, str):
        raise SoundCloudError("Ongeldige stream- of CDN-URL.")

    trimmed = url.strip()
    try:
        parsed = urllib.parse.urlparse(trimmed)
    except Exception as exc:
        raise SoundCloudError(f"Ongeldige stream-URL-syntaxis: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise SoundCloudError(
            f"Onveilig URL-schema '{parsed.scheme}://' voor audiostream: behoort niet tot SoundCloud of het SoundCloud CDN. Alleen 'https://' is toegestaan."
        )

    if parsed.username or parsed.password:
        raise SoundCloudError("Inloggegevens in de stream-URL zijn niet toegestaan.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SoundCloudError("Geen geldig hostadres in stream-URL.")

    # Blokkeer localhost expliciet
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise SoundCloudError(
            f"Onveilige audiostream-locatie: localhost '{hostname}' behoort niet tot SoundCloud of het SoundCloud CDN."
        )

    # Blokkeer IP-adressen (zoals 127.0.0.1, 169.254.169.254, etc.)
    try:
        ipaddress.ip_address(hostname)
        raise SoundCloudError(
            f"Onveilige audiostream-locatie: IP-adres '{hostname}' behoort niet tot SoundCloud of het SoundCloud CDN."
        )
    except ValueError:
        pass

    is_valid_host = any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in ALLOWED_CDN_DOMAINS
    )
    if not is_valid_host:
        raise SoundCloudError(
            f"Onveilige audiostream-locatie: domein '{hostname}' behoort niet tot SoundCloud of het SoundCloud CDN."
        )

    return trimmed


def sanitize_filename(name: str, extension: str = "") -> str:
    """
    Schoont een bestandsnaam grondig op tegen Path Traversal en ongeldige Windows-tekens.

    - Verwijdert padscheidingstekens (/, \\, ..) en stuurtekens.
    - Vervangt ongeldige Windows-tekens (<>:"/\\|?*).
    - Voorkomt gereserveerde Windows-namen (CON, PRN, AUX, NUL, COM1-9, LPT1-9).
    - Begrenst de bestandsnaam op maximaal 120 tekens (exclusief extensie).
    - Zorgt voor een geldige extensie en veilige fallback als de naam leeg zou raken.

    Args:
        name: De gewenste basisbestandsnaam of volledige bestandsnaam.
        extension: Optionele extensie (bijv. '.mp3', '.zip').

    Returns:
        Veilige bestandsnaam met extensie.
    """
    if not name or not isinstance(name, str):
        raw_name = "track"
    else:
        raw_name = name.strip()

    # Normaliseer extensie
    clean_ext = ""
    if extension:
        clean_ext = ("." + extension.lstrip(".")).lower()

    # Als de naam al eindigt op de extensie, strip die van de basisnaam
    if clean_ext and raw_name.lower().endswith(clean_ext):
        raw_name = raw_name[:-len(clean_ext)]
    elif "." in raw_name and not clean_ext:
        parts = raw_name.rsplit(".", 1)
        raw_name, clean_ext = parts[0], f".{parts[1].lower()}"

    # Verwijder directory traversal patronen (..)
    while ".." in raw_name:
        raw_name = raw_name.replace("..", "")

    # Vervang ongeldige Windows tekens en padscheidingstekens door een underscore
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]', '_', raw_name)

    # Vervang meervoudige spaties of underscores door een enkele spatie
    sanitized = re.sub(r'[\s_]+', ' ', sanitized).strip(" ._")

    # Begrens op maximaal 120 tekens (exclusief extensie)
    if len(sanitized) > MAX_FILENAME_LENGTH:
        sanitized = sanitized[:MAX_FILENAME_LENGTH].rstrip(" ._")

    # Controleer op lege naam of gereserveerde Windows bestandsnamen
    if not sanitized:
        sanitized = "track"
    elif sanitized.upper() in WINDOWS_RESERVED_NAMES:
        sanitized = f"track_{sanitized}"

    return f"{sanitized}{clean_ext}"
