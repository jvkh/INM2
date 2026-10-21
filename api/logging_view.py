"""Read and reset the service-specific log files shown in the UI."""

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query

from common.logging_setup import configure_file_logging


router = APIRouter()
LOG_DIRECTORY = Path(
    os.environ.get("INM2_LOG_DIR", str(Path(__file__).resolve().parent.parent / "logs"))
)
LOG_FILES = {
    "collector": ("collector.log",),
    "api": ("api.log",),
    "ui_access": ("ui-access.log",),
    "ui_error": ("ui-error.log",),
}
MAX_LOG_BYTES = 2 * 1024 * 1024


def _service_files(service: str) -> list[Path]:
    current = LOG_DIRECTORY / LOG_FILES[service][0]
    if service in {"api", "collector"}:
        rotated = [Path(f"{current}.{index}") for index in range(3, 0, -1)]
    else:
        rotated = []
    return [path for path in rotated + [current] if path.is_file()]


@router.get("/logs")
def get_logs(
    service: Literal["collector", "api", "ui_access", "ui_error"] = Query(default="collector"),
    limit: int = Query(default=2000, ge=1, le=10000),
) -> dict[str, Any]:
    """Return the most recent lines from one service log, with bounded output."""
    chunks: list[bytes] = []
    remaining = MAX_LOG_BYTES
    truncated = False
    for path in reversed(_service_files(service)):
        try:
            if remaining <= 0:
                truncated = True
                break
            size = path.stat().st_size
            with path.open("rb") as stream:
                start = max(0, size - remaining)
                if start:
                    stream.seek(start)
                    stream.readline()  # Discard a partial first line.
                    truncated = True
                else:
                    stream.seek(0)
                chunk = stream.read(remaining)
            chunks.append(chunk)
            remaining -= len(chunk)
        except OSError:
            continue
    content = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    lines = content.splitlines()
    if len(lines) > limit:
        lines = lines[-limit:]
        truncated = True
    return {"service": service, "content": "\n".join(lines), "truncated": truncated}


@router.delete("/logs")
def reset_logs(
    service: Literal["collector", "api", "ui_access", "ui_error"] = Query(...),
) -> dict[str, Any]:
    """Clear the selected log while preserving its inode for active writers."""
    files = LOG_FILES[service]
    for filename in files:
        path = LOG_DIRECTORY / filename
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            for index in range(1, 4):
                Path(f"{path}.{index}").unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Could not reset log file") from exc
    if service in {"api", "collector"}:
        configure_file_logging(service)
    return {"service": service, "reset": True}
