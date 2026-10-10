"""Incremental reader for Traefik JSON access logs."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


class TraefikReader:
    """Read complete JSON lines and remove only successfully imported lines."""

    def __init__(self, path: str | Path, save_margin_characters: int) -> None:
        if save_margin_characters <= 0:
            raise ValueError("Save margin must be greater than zero")
        self.path = Path(path)
        self.save_margin_characters = save_margin_characters

    def read(self, callback: Callable[[dict[str, Any]], None]) -> int:
        """Pass safe complete log records to ``callback`` and return their count.

        A successfully handled prefix is removed even if a later line fails, so
        already committed records are not imported again on the next run.
        """
        imported = 0
        consumed_bytes = 0
        with self.path.open("r+b") as log_file:
            file_size = log_file.seek(0, 2)
            safe_end = max(0, file_size - self.save_margin_characters)
            log_file.seek(0)

            try:
                while log_file.tell() < safe_end:
                    line_start = log_file.tell()
                    line = log_file.readline()
                    if not line or not line.endswith(b"\n"):
                        break
                    if log_file.tell() > safe_end:
                        break

                    record = json.loads(line.decode("utf-8"))
                    if not isinstance(record, dict):
                        raise ValueError(f"Expected a JSON object in {self.path} at byte {line_start}")
                    callback(record)
                    consumed_bytes = log_file.tell()
                    imported += 1
            finally:
                if consumed_bytes:
                    self._remove_prefix(log_file, consumed_bytes)

        return imported

    @staticmethod
    def _remove_prefix(log_file: Any, prefix_size: int) -> None:
        """Shift the unread tail to the beginning and truncate the file."""
        log_file.seek(0, 2)
        file_size = log_file.tell()
        source = prefix_size
        target = 0
        while source < file_size:
            log_file.seek(source)
            chunk = log_file.read(min(1024 * 1024, file_size - source))
            if not chunk:
                break
            log_file.seek(target)
            log_file.write(chunk)
            source += len(chunk)
            target += len(chunk)
        log_file.truncate(target)
        log_file.flush()
