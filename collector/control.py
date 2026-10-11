"""Private HTTP control endpoints for the collector container."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException

if TYPE_CHECKING:
    from collector.main import CollectorApplication


def create_control_app(collector: CollectorApplication) -> FastAPI:
    """Create the internal control API bound to the running collector."""
    app = FastAPI(
        title="Collector Control API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.put("/internal/maintenance", status_code=202)
    def request_maintenance() -> dict[str, str]:
        if not collector.request_maintenance():
            raise HTTPException(status_code=409, detail="Collector is busy")
        return {"status": "accepted", "activity": "Maintenance"}

    @app.put("/internal/import", status_code=202)
    def request_import() -> dict[str, str]:
        if not collector.request_import():
            raise HTTPException(status_code=409, detail="Collector is busy")
        return {"status": "accepted", "activity": "Import"}

    return app
