import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging() -> None:
    """Keep stdout logs, and optionally mirror app logs to a persistent file."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    log_dir = os.getenv("APP_LOG_DIR")
    if not log_dir:
        return

    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_file = (path / "speakup.log").resolve()
    if any(
        isinstance(handler, RotatingFileHandler)
        and getattr(handler, "baseFilename", "") == str(log_file)
        for handler in root.handlers
    ):
        return

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler = RotatingFileHandler(
        log_file,
        maxBytes=int(os.getenv("APP_LOG_MAX_BYTES", str(20 * 1024 * 1024))),
        backupCount=int(os.getenv("APP_LOG_BACKUP_COUNT", "10")),
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    root.addHandler(handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        if not logger.propagate:
            logger.addHandler(handler)
