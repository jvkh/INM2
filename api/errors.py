"""Centralized API error responses."""

import logging
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.dependencies import DatabaseUnavailable


logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register consistent handlers for unavailable services and bugs."""

    @app.exception_handler(DatabaseUnavailable)
    async def database_unavailable_handler(
        request: Request, exc: DatabaseUnavailable
    ) -> JSONResponse:
        logger.warning("Database unavailable while handling %s", request.url.path)
        return _error_response(503, "database_unavailable", "Database temporarily unavailable")

    @app.exception_handler(sqlite3.OperationalError)
    async def database_operational_error_handler(
        request: Request, exc: sqlite3.OperationalError
    ) -> JSONResponse:
        logger.exception("Database operation failed while handling %s", request.url.path)
        return _error_response(503, "database_unavailable", "Database temporarily unavailable")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error while handling %s", request.url.path)
        return _error_response(500, "internal_server_error", "Internal server error")
