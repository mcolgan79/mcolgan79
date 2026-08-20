"""Logging: pretty on the terminal, structured and rotating on disk."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler

from .config import LoggingConfig

_CONFIGURED = False


def setup_logging(
    config: LoggingConfig, console: Console | None = None, level: str | None = None
) -> logging.Logger:
    """Attach a Rich console handler and a rotating file handler to the root."""
    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED:
        return logging.getLogger("autotrader")

    resolved_level = (level or config.level).upper()
    root.setLevel(logging.DEBUG)  # handlers do the filtering

    console_handler = RichHandler(
        console=console or Console(stderr=True),
        show_path=False,
        rich_tracebacks=True,
        omit_repeated_times=False,
    )
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))
    root.addHandler(console_handler)

    log_path = config.resolved_file()
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=config.max_bytes, backupCount=config.backups
        )
        file_handler.setLevel(logging.DEBUG if resolved_level == "DEBUG" else logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(file_handler)

    # The SDKs are chatty at DEBUG and we rarely want their HTTP noise.
    for noisy in ("urllib3", "httpx", "httpcore", "alpaca"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return logging.getLogger("autotrader")
