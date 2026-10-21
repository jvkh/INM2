"""Incremental reader for Traefik JSON access logs, including rotated files."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TraefikReader:
    """Read complete JSON lines from a file, resuming at a persisted offset."""

    FINGERPRINT_BYTES = 65536

    def __init__(self, path: str | Path, save_margin_characters: int) -> None:
        if save_margin_characters <= 0:
            raise ValueError("Save margin must be greater than zero")
        self.path = Path(path)
        self.save_margin_characters = save_margin_characters
        self.skipped_count = 0

    @staticmethod
    def identity(path: str | Path) -> str:
        stat = Path(path).stat()
        return f"{stat.st_dev}:{stat.st_ino}"

    @classmethod
    def fingerprint(cls, path: str | Path) -> str | None:
        """Fingerprint the first complete log line, stable as the file grows."""
        path = Path(path)
        with path.open("rb") as raw_file:
            log_file = gzip.GzipFile(fileobj=raw_file) if path.name.endswith(".gz") else raw_file
            try:
                return cls._fingerprint_stream(log_file)
            finally:
                if log_file is not raw_file:
                    log_file.close()

    @classmethod
    def _fingerprint_stream(cls, log_file: Any) -> str | None:
        first_line = log_file.readline(cls.FINGERPRINT_BYTES + 1)
        if not first_line or (len(first_line) <= cls.FINGERPRINT_BYTES and not first_line.endswith(b"\n")):
            return None
        return hashlib.sha256(first_line[: cls.FINGERPRINT_BYTES]).hexdigest()

    def read(
        self,
        callback: Callable[[dict[str, Any], int, str, str | None], bool | None],
        *,
        start_offset: int = 0,
        file_identity: str | None = None,
        on_position_reset: Callable[[str, str | None], None] | None = None,
        on_invalid_line: Callable[[int, str, str | None], None] | None = None,
        file_fingerprint: str | None = None,
        sealed: bool = False,
    ) -> int:
        """Read complete lines; sealed rotated files are read through EOF.

        Offsets for gzip files refer to the uncompressed stream. The saved
        fingerprint helps detect an inode that has been reused for another file.
        """
        imported = skipped = 0
        compressed = self.path.name.endswith(".gz")
        with self.path.open("rb") as raw_file:
            stat = os.fstat(raw_file.fileno())
            current_identity = f"{stat.st_dev}:{stat.st_ino}"
            log_file = gzip.GzipFile(fileobj=raw_file) if compressed else raw_file
            try:
                current_fingerprint = self._fingerprint_stream(log_file)
                log_file.seek(0)
                file_size = None if compressed else stat.st_size
                reset_reason = None
                if start_offset < 0:
                    reset_reason = "invalid saved offset"
                elif file_identity is not None and file_identity != current_identity:
                    reset_reason = "file identity changed"
                elif (
                    file_fingerprint is not None
                    and file_fingerprint != current_fingerprint
                ):
                    reset_reason = "file fingerprint changed"
                elif file_size is not None and file_size < start_offset:
                    reset_reason = "file became shorter than the saved offset"
                elif file_identity is None:
                    reset_reason = "no saved file identity"
                if reset_reason is not None:
                    if file_identity is not None:
                        logger.warning(
                            "Resetting log position for %s from byte %d to 0: %s",
                            self.path, start_offset, reset_reason,
                        )
                    start_offset = 0
                    if on_position_reset is not None:
                        on_position_reset(current_identity, current_fingerprint)

                safe_end = (
                    file_size if sealed else max(0, file_size - self.save_margin_characters)
                )
                log_file.seek(start_offset)
                while safe_end is None or log_file.tell() < safe_end:
                    line_start = log_file.tell()
                    line = log_file.readline()
                    if not line or not line.endswith(b"\n"):
                        break
                    if not sealed and log_file.tell() > safe_end:
                        break
                    try:
                        record = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        skipped += 1
                        logger.warning(
                            "Skipping malformed JSON in %s at byte %d: %s",
                            self.path, line_start, exc,
                        )
                        if on_invalid_line is not None:
                            on_invalid_line(log_file.tell(), current_identity, current_fingerprint)
                        continue
                    if not isinstance(record, dict):
                        skipped += 1
                        logger.warning(
                            "Skipping non-object JSON record in %s at byte %d",
                            self.path, line_start,
                        )
                        if on_invalid_line is not None:
                            on_invalid_line(log_file.tell(), current_identity, current_fingerprint)
                        continue
                    imported_record = callback(
                        record, log_file.tell(), current_identity, current_fingerprint
                    )
                    if imported_record is False:
                        skipped += 1
                    else:
                        imported += 1
            finally:
                if compressed:
                    log_file.close()

        self.skipped_count = skipped
        return imported
