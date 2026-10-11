"""Burst listing and summary endpoint."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request

from api.dependencies import get_database


router = APIRouter()


def _utc_timestamp(value: datetime) -> str:
    """Normalize timestamps to the UTC format stored by the collector."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/burst_requests/{id}")
def get_burst_requests(
    request: Request,
    id: int = Path(ge=1, description="Burst ID"),
) -> dict[str, Any]:
    """Return a burst and its requests, matched by actor, host, and time."""
    database = get_database(request)
    burst_rows = database.query(
        """SELECT b.*, a.ip AS actor_ip, a.country, a.provider, a.asn, a.city,
                  h.name AS host
           FROM burst AS b
           JOIN actor AS a ON a.actor_id = b.actor_id
           LEFT JOIN host AS h ON h.host_id = b.host_id
           WHERE b.burst_id = ?""",
        (id,),
    )
    if not burst_rows:
        raise HTTPException(status_code=404, detail="Burst not found")

    burst = burst_rows[0]
    requests = database.query(
        """SELECT r.*
           FROM request AS r
           WHERE r.actor_id = ?
             AND r.host_id IS ?
             AND r.start_utc >= ?
             AND r.start_utc <= ?
           ORDER BY r.start_utc, r.request_id""",
        (burst["actor_id"], burst["host_id"], burst["start_time"], burst["end_time"]),
    )
    return {"burst": burst, "requests": requests, "total": len(requests)}


@router.get("/bursts/{id}")
def get_burst_requests(
    request: Request,
    id: int = Path(ge=1, description="Burst ID"),
) -> dict[str, Any]:
    """Return a burst."""
    database = get_database(request)
    burst_rows = database.query(
        """SELECT b.*, a.ip AS actor_ip, a.country, a.provider, a.asn, a.city,
                  h.name AS host
           FROM burst AS b
           JOIN actor AS a ON a.actor_id = b.actor_id
           LEFT JOIN host AS h ON h.host_id = b.host_id
           WHERE b.burst_id = ?""",
        (id,),
    )
    if not burst_rows:
        raise HTTPException(status_code=404, detail="Burst not found")

    return burst_rows[0]

@router.get("/bursts")
def get_bursts(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    actor: str | None = Query(default=None, min_length=1, description="Actor IP substring"),
    actor_id: int | None = Query(default=None, ge=1),
    host: str | None = Query(default=None, min_length=1),
    country: str | None = Query(default=None, min_length=1),
    provider: str | None = Query(default=None, min_length=1),
    asn: str | None = Query(default=None, min_length=1),
    city: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return a burst summary and matching bursts for a time range."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["b.start_time >= ?", "b.start_time < ?"]
    parameters: list[Any] = [start, end]
    for column, value in (
        ("a.ip", actor),
        ("h.name", host),
        ("a.country", country),
        ("a.provider", provider),
        ("a.asn", asn),
        ("a.city", city),
    ):
        if value is not None:
            conditions.append(f"{column} LIKE ?")
            parameters.append(f"%{value}%")
    if actor_id is not None:
        conditions.append("b.actor_id = ?")
        parameters.append(actor_id)

    where_clause = " AND ".join(conditions)
    database = get_database(request)
    from_clause = """FROM burst AS b
                     JOIN actor AS a ON a.actor_id = b.actor_id
                     LEFT JOIN host AS h ON h.host_id = b.host_id"""
    filtered = f"SELECT b.*, a.ip AS actor_ip, a.country, a.provider, a.asn, a.city, h.name AS host {from_clause} WHERE {where_clause}"

    aggregate_rows = database.query(
        f"""WITH filtered AS ({filtered})
            SELECT COUNT(*) AS burst_count,
                   COUNT(DISTINCT actor_id) AS actor_count,
                   COALESCE(SUM(read_count + write_count + other_count), 0) AS request_count,
                   COALESCE(SUM(read_count), 0) AS read_count,
                   COALESCE(SUM(write_count), 0) AS write_count,
                   COALESCE(SUM(other_count), 0) AS other_count,
                   AVG(read_count + write_count + other_count) AS avg_requests_per_burst,
                   MAX(read_count + write_count + other_count) AS max_requests_per_burst,
                   AVG((julianday(end_time) - julianday(start_time)) * 86400.0) AS avg_duration_seconds,
                   MAX((julianday(end_time) - julianday(start_time)) * 86400.0) AS max_duration_seconds,
                   AVG(avg_count) AS avg_requests_per_second
            FROM filtered""",
        parameters,
    )
    summary = aggregate_rows[0]
    burst_count = summary["burst_count"]
    actor_count = summary["actor_count"]
    summary.update(
        {
            "avg_bursts_per_actor": burst_count / actor_count if actor_count else 0,
            "median_requests_per_burst": _median(
                database, filtered, parameters,
                "read_count + write_count + other_count",
            ),
            "median_duration_seconds": _median(
                database, filtered, parameters,
                "(julianday(end_time) - julianday(start_time)) * 86400.0",
            ),
            "median_bursts_per_actor": _median_bursts_per_actor(
                database, filtered, parameters,
            ),
            "max_bursts_per_actor": _max_bursts_per_actor(
                database, filtered, parameters,
            ),
        }
    )

    items = database.query(
        f"""{filtered}
            ORDER BY b.start_time, b.burst_id
            LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    return {
        "summary": summary,
        "items": items,
        "limit": limit,
        "offset": offset,
        "from": start,
        "to": end,
    }


def _median(database: Any, filtered: str, parameters: list[Any], expression: str) -> float | None:
    """Calculate a median with SQLite window functions without loading all rows."""
    rows = database.query(
        f"""WITH filtered AS ({filtered}),
            values_to_rank AS (SELECT {expression} AS value FROM filtered),
            ranked AS (
                SELECT value, ROW_NUMBER() OVER (ORDER BY value) AS row_number,
                       COUNT(*) OVER () AS row_count
                FROM values_to_rank
            )
            SELECT AVG(value) AS median FROM ranked
            WHERE row_number IN ((row_count + 1) / 2, (row_count + 2) / 2)""",
        parameters,
    )
    return rows[0]["median"]


def _median_bursts_per_actor(
    database: Any, filtered: str, parameters: list[Any]
) -> float | None:
    """Calculate the median number of matching bursts per actor."""
    rows = database.query(
        f"""WITH filtered AS ({filtered}),
            actor_counts AS (
                SELECT actor_id, COUNT(*) AS burst_count
                FROM filtered GROUP BY actor_id
            ),
            ranked AS (
                SELECT burst_count, ROW_NUMBER() OVER (ORDER BY burst_count) AS row_number,
                       COUNT(*) OVER () AS row_count
                FROM actor_counts
            )
            SELECT AVG(burst_count) AS median FROM ranked
            WHERE row_number IN ((row_count + 1) / 2, (row_count + 2) / 2)""",
        parameters,
    )
    return rows[0]["median"]


def _max_bursts_per_actor(
    database: Any, filtered: str, parameters: list[Any]
) -> int:
    """Calculate the largest number of matching bursts for one actor."""
    rows = database.query(
        f"""WITH filtered AS ({filtered}),
            actor_counts AS (
                SELECT actor_id, COUNT(*) AS burst_count
                FROM filtered GROUP BY actor_id
            )
            SELECT COALESCE(MAX(burst_count), 0) AS maximum FROM actor_counts""",
        parameters,
    )
    return rows[0]["maximum"]
