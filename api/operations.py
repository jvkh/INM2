"""API endpoints that ask the collector to run scheduled operations."""

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen

from fastapi import APIRouter
from fastapi.responses import JSONResponse


router = APIRouter()
logger = logging.getLogger(__name__)
CONTROL_URL = os.environ.get("COLLECTOR_CONTROL_URL", "http://collector:8001").rstrip("/")


def _trigger_collector_operation(operation: str) -> Any:
    request = URLRequest(
        f"{CONTROL_URL}/internal/{operation}",
        data=b"",
        method="PUT",
        headers={"Content-Length": "0"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 409:
            return JSONResponse(
                status_code=409,
                content={"error": {"code": "collector_busy", "message": "Collector is busy"}},
            )
        logger.warning("Collector rejected the %s operation with HTTP %s", operation, exc.code)
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "collector_error", "message": "Collector rejected the operation"}},
        )
    except (URLError, TimeoutError, OSError):
        logger.exception("Collector unavailable while requesting %s", operation)
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "collector_unavailable", "message": "Collector is unavailable"}},
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.exception("Collector returned an invalid response to %s", operation)
        return JSONResponse(
            status_code=502,
            content={"error": {"code": "collector_error", "message": "Invalid response from collector"}},
        )


@router.put("/maintenance", status_code=202)
def trigger_maintenance() -> Any:
    """Ask the collector to run maintenance if it is idle."""
    return _trigger_collector_operation("maintenance")


@router.put("/import", status_code=202)
def trigger_import() -> Any:
    """Ask the collector to start an import if it is idle."""
    return _trigger_collector_operation("import")
