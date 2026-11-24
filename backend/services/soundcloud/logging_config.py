"""
SoundCloud logging configuratie.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Project root: soundcloud/ -> services/ -> backend/ -> soundcloud-scraper/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG_FILE = LOGS_DIR / "error.log"

logger = logging.getLogger("soundcloud_scraper")
if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(
        str(ERROR_LOG_FILE),
        maxBytes=1024 * 1024,  # max 1 MB
        backupCount=5,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
