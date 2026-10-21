"""Distinct request paths matching a global search term."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database

router = APIRouter()


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/request_paths")
def get_request_paths(
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    search: str = Query(min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return distinct request paths matching a substring within the selected time range."""
    start, end = _utc_text(from_), _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    rows = get_database(request).query(
        """SELECT r.request_path AS path, COUNT(*) AS request_count,
                  MAX(r.start_utc) AS last_seen
           FROM request AS r
           WHERE r.start_utc >= ? AND r.start_utc < ?
             AND r.request_path LIKE ?
           GROUP BY r.request_path
           ORDER BY request_count DESC, last_seen DESC, r.request_path COLLATE NOCASE ASC
           LIMIT ?""",
        [start, end, f"%{search}%", limit],
    )
    return {"items": rows, "from": start, "to": end, "search": search, "limit": limit}
