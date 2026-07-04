import logging
from logging.handlers import TimedRotatingFileHandler

from logging_config import configure_logging


def test_configure_logging_adds_daily_rotating_file_handler(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_LOG_BACKUP_COUNT", "7")
    monkeypatch.setenv("APP_LOG_ROTATE_WHEN", "midnight")

    root = logging.getLogger()
    before = list(root.handlers)
    try:
        root.handlers = []
        configure_logging()
        configure_logging()

        file_handlers = [
            h for h in root.handlers
            if isinstance(h, TimedRotatingFileHandler)
        ]
        assert len(file_handlers) == 1
        assert file_handlers[0].backupCount == 7
        assert file_handlers[0].suffix == "%Y-%m-%d"
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers = before
