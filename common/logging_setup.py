"""Configure a service-specific rotating log file alongside container output."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_file_logging(service: str) -> None:
    """Add one process-local rotating file handler for the named service."""
    directory = Path(
        os.environ.get("INM2_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = (directory / f"{service}.log").resolve()
        root = logging.getLogger()
        handler = next(
            (entry for entry in root.handlers if getattr(entry, "baseFilename", None) == str(path)),
            None,
        )
        if handler is None:
            handler = RotatingFileHandler(
                path,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            root.addHandler(handler)
        root.setLevel(min(root.level or logging.INFO, logging.INFO))
        for name in ("uvicorn.error", "uvicorn.access"):
            service_logger = logging.getLogger(name)
            if handler not in service_logger.handlers:
                service_logger.addHandler(handler)
            service_logger.propagate = False
    except OSError:
        logging.getLogger(__name__).exception("Could not configure %s log file", service)
