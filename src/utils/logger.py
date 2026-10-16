"""Central logger: console + rotating file inside logs/."""

import logging
import sys
from logging.handlers import RotatingFileHandler

from src.config import LOGS_DIR

_configured = set()


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    Windows-friendly rotation.

    Renaming an open log file fails on Windows (WinError 32) — both for this
    process and for any second process writing to the same log. Instead of
    spamming "Logging error" tracebacks, fall back to truncating the stream
    in place, which always works.
    """

    def doRollover(self) -> None:                    # pragma: no cover
        try:
            super().doRollover()
        except OSError:
            try:
                self.stream.seek(0)
                self.stream.truncate()
            except OSError:
                pass


def get_logger(name: str, filename: str = "earthscape.log") -> logging.Logger:
    """Return a configured logger. Safe to call repeatedly for the same name."""
    if name in _configured:
        return logging.getLogger(name)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    fh = SafeRotatingFileHandler(
        LOGS_DIR / filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.propagate = False
    _configured.add(name)
    return logger
