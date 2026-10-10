"""Actor listing endpoint."""

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


@router.get("/actors/{id}")
def get_actor(
    request: Request,
    id: int = Path(ge=1, description="Actor ID"),
) -> dict[str, Any]:
    """Return one actor and its lifetime request and burst counts."""
    database = get_database(request)
    rows = database.query(
        """SELECT a.actor_id, a.ip, a.first_time, a.last_time,
                  a.provider, a.asn, a.city, a.country,
                  (SELECT COUNT(*) FROM request AS r WHERE r.actor_id = a.actor_id)
                      AS request_count,
                  (SELECT COUNT(*) FROM burst AS b WHERE b.actor_id = a.actor_id)
                      AS burst_count
           FROM actor AS a
           WHERE a.actor_id = ?""",
        (id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Actor not found")
    return rows[0]


@router.get("/actors")
def get_actors(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    new_only: bool = Query(default=False, description="Only actors first seen in this period"),
    provider: str | None = Query(default=None, min_length=1),
    country: str | None = Query(default=None, min_length=1),
    city: str | None = Query(default=None, min_length=1),
    asn: str | None = Query(default=None, min_length=1),
    ip: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return actors active in the time range, optionally only newly seen ones."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    parameters: list[Any] = [start, end]
    if new_only:
        conditions.extend(["a.first_time >= ?", "a.first_time < ?"])
        parameters.extend([start, end])
    for column, value in (
        ("a.provider", provider),
        ("a.country", country),
        ("a.city", city),
        ("a.asn", asn),
        ("a.ip", ip),
    ):
        if value is not None:
            conditions.append(f"{column} LIKE ?")
            parameters.append(f"%{value}%")
    where_clause = " AND ".join(conditions)
    database = get_database(request)
    joins = """FROM actor AS a
               JOIN request AS r ON r.actor_id = a.actor_id"""

    total_rows = database.query(
        f"SELECT COUNT(DISTINCT a.actor_id) AS total {joins} WHERE {where_clause}",
        parameters,
    )
    items = database.query(
        f"""SELECT a.actor_id, a.ip, a.first_time, a.last_time,
                      a.provider, a.asn, a.city, a.country,
                      COUNT(r.request_id) AS request_count
               {joins}
               WHERE {where_clause}
               GROUP BY a.actor_id
               ORDER BY a.first_time, a.actor_id
               LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    return {
        "items": items,
        "total": total_rows[0]["total"],
        "limit": limit,
        "offset": offset,
        "from": start,
        "to": end,
        "new_only": new_only,
    }
