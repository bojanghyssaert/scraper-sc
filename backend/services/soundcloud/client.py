"""
HTTP-client en Client-ID beheer voor SoundCloud.
"""

import re
import sys
from typing import Callable
import requests

from .constants import HEADERS, TIMEOUT
from .exceptions import SoundCloudError
from .logging_config import logger

_cached_client_id: str | None = None
_on_client_id_reset_callbacks: list[Callable[[], None]] = []
_on_client_id_updated_callbacks: list[Callable[[str], None]] = []


def register_reset_callback(cb: Callable[[], None]) -> None:
    """Registreert een callback die wordt aangeroepen wanneer de client_id wordt gereset."""
    if cb not in _on_client_id_reset_callbacks:
        _on_client_id_reset_callbacks.append(cb)


def register_update_callback(cb: Callable[[str], None]) -> None:
    """Registreert een callback die wordt aangeroepen wanneer een nieuwe client_id is ingesteld."""
    if cb not in _on_client_id_updated_callbacks:
        _on_client_id_updated_callbacks.append(cb)


def reset_client_id() -> None:
    """
    Maakt de gecachete client_id ongeldig zodat bij een volgend verzoek
    een nieuwe client_id wordt opgehaald.
    """
    global _cached_client_id
    _cached_client_id = None
    for cb in list(_on_client_id_reset_callbacks):
        try:
            cb()
        except Exception:
            pass


def _set_cached_client_id(cid: str | None) -> None:
    """Stelt de gecachete client_id in en verwittigt geregistreerde callbacks."""
    global _cached_client_id
    _cached_client_id = cid
    if cid is not None:
        for cb in list(_on_client_id_updated_callbacks):
            try:
                cb(cid)
            except Exception:
                pass


def get_cached_client_id() -> str:
    """
    Haalt de gecachete client_id op of vraagt een nieuwe op als deze nog niet gecached is.

    Returns:
        De 32-tekens client_id string.

    Raises:
        SoundCloudError: Als het ophalen van een client_id mislukt.
    """
    global _cached_client_id
    if not _cached_client_id:
        this_mod = sys.modules[__name__]
        fresh_id = getattr(this_mod, "get_client_id", get_client_id)()
        _set_cached_client_id(fresh_id)
    return _cached_client_id


def get_client_id() -> str:
    """
    Haalt dynamisch de actieve client_id op uit de SoundCloud-frontend JS.

    Returns:
        De 32-tekens client_id string.

    Raises:
        SoundCloudError: Als de client_id niet gevonden kan worden.
    """
    try:
        response = requests.get("https://soundcloud.com", headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SoundCloudError(
            f"Kan SoundCloud homepage niet bereiken: {exc}"
        ) from exc

    script_urls = re.findall(
        r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"></script>',
        response.text,
    )
    if not script_urls:
        raise SoundCloudError("Geen JS-bestanden gevonden op de SoundCloud-homepage.")

    for url in script_urls:
        try:
            js_resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if js_resp.status_code == 200:
                match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js_resp.text)
                if match:
                    return match.group(1)
        except requests.RequestException:
            continue

    raise SoundCloudError(
        "Kon geen geldige client_id vinden in de SoundCloud JS-bestanden."
    )


def _fetch_with_retry(
    url: str,
    params: dict | None = None,
    client_id: str | None = None,
    timeout: int = TIMEOUT,
) -> tuple[requests.Response, str]:
    """
    Voert een GET-verzoek uit met een client_id.
    Als SoundCloud een HTTP 401 of 403 retourneert, wordt reset_client_id()
    aangeroepen, een verse client_id opgehaald via get_client_id(),
    en het verzoek eenmalig herhaald.

    Returns:
        tuple[requests.Response, str]: (respons, gebruikte_client_id)
    """
    this_mod = sys.modules[__name__]
    fn_get_cached = getattr(this_mod, "get_cached_client_id", get_cached_client_id)
    fn_reset = getattr(this_mod, "reset_client_id", reset_client_id)
    fn_get_fresh = getattr(this_mod, "get_client_id", get_client_id)

    active_client_id = client_id or fn_get_cached()
    req_params = dict(params or {}) if params is not None else None

    # Bouw req_url en req_params op
    if "client_id=" in url:
        req_url = re.sub(r"([?&]client_id=)[^&]+", rf"\g<1>{active_client_id}", url)
    elif req_params is not None:
        req_url = url
        req_params["client_id"] = active_client_id
    else:
        req_url = url
        req_params = {"client_id": active_client_id}

    try:
        resp = requests.get(req_url, params=req_params, headers=HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise SoundCloudError(f"Netwerkfout bij SoundCloud-verzoek: {exc}") from exc

    # Bij 401 of 403: maak cache ongeldig, haal verse client_id op en herhaal één keer
    if resp.status_code in (401, 403):
        fn_reset()
        active_client_id = fn_get_fresh()
        _set_cached_client_id(active_client_id)

        if "client_id=" in url:
            req_url = re.sub(r"([?&]client_id=)[^&]+", rf"\g<1>{active_client_id}", url)
        else:
            req_params["client_id"] = active_client_id

        try:
            resp = requests.get(req_url, params=req_params, headers=HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            raise SoundCloudError(f"Netwerkfout na vernieuwen client_id: {exc}") from exc

    return resp, active_client_id
