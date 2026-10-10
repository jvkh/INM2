"""Shared API dependencies."""

from fastapi import Request

from common.database import Database


class DatabaseUnavailable(Exception):
    """Raised when the API process has no usable database connection."""


def get_database(request: Request) -> Database:
    """Return the app database or signal that it is currently unavailable."""
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise DatabaseUnavailable
    return database
