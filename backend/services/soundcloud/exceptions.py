"""
SoundCloud uitzonderingsklassen.
"""

import sys
from .logging_config import logger


class SoundCloudError(Exception):
    """Domein-specifieke fout voor SoundCloud-bewerkingen."""

    def __init__(self, message: str = "", *args):
        super().__init__(message, *args)
        has_exc = sys.exc_info()[0] is not None
        logger.error(f"{self.__class__.__name__}: {message}", exc_info=has_exc)


class SoundCloudDRMError(SoundCloudError):
    """Domein-specifieke fout voor DRM-beveiligde SoundCloud tracks."""
