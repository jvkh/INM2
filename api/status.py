"""Status endpoint for the API and collector."""

import logging
from typing import Any

from fastapi import APIRouter, Request

from common.status import CollectorStatus


logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
def get_status(request: Request) -> dict[str, Any]:
    """Report API health, stored collector status, and safe configuration."""
    fallback = {
        "status": "degraded",
        "database": "unavailable",
        "collector_status": {
            "available": False,
            "last_import": None,
            "activity": "Unknown",
            "import_file": "",
            "last_import_file": "",
            "import_count": 0,
        },
        "environment": {},
    }
    try:
        database = request.app.state.database
        if database is None:
            return fallback

        database.query("SELECT 1")
        collector_status = CollectorStatus.read_snapshot(database)
        environment = collector_status.pop("environment", {})
        collector_status["available"] = True
        return {
            "status": "ok",
            "database": "ok",
            "collector_status": collector_status,
            "environment": environment,
        }
    except Exception:
        logger.exception("Could not read API status")
        return fallback
