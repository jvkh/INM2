"""Actor listing endpoint."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from api.dependencies import get_database
from common.search import parse_search

router = APIRouter()


def _utc_timestamp(value: datetime) -> str:
    """Normalize timestamps to the UTC format stored by the collector."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _append_actor_search(
    value: str,
    conditions: list[str],
    parameters: list[Any],
    *,
    include_country: bool,
    start: str,
    end: str,
) -> None:
    field, term = parse_search(value)
    if not term:
        conditions.append("0")
    elif field is None:
        columns = ["a.ip", "COALESCE(a.city, '')", "COALESCE(a.provider, '')", "COALESCE(a.asn, '')"]
        if include_country:
            columns.append("COALESCE(a.country, '')")
        conditions.append("(" + " OR ".join(f"{column} LIKE ?" for column in columns) + ")")
        parameters.extend([f"%{term}%"] * len(columns))
    elif field in {"ip", "country", "city", "provider", "asn"}:
        column = {"ip": "a.ip", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn"}[field]
        conditions.append(f"COALESCE({column}, '') LIKE ?")
        parameters.append(f"%{term}%")
    elif field in {"host", "path", "category", "method", "status", "scheme", "user_agent"}:
        if field == "host":
            match = "EXISTS (SELECT 1 FROM host AS sh WHERE sh.host_id = sr.host_id AND sh.name LIKE ?)"
        elif field == "category":
            match = "EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id = src.category_id WHERE src.request_id = sr.request_id AND sc.category_name LIKE ?)"
        else:
            column = {"path": "request_path", "method": "request_method", "status": "downstream_status", "scheme": "request_scheme", "user_agent": "user_agent"}[field]
            match = f"COALESCE(sr.{column}, '') LIKE ?"
        conditions.append(
            f"EXISTS (SELECT 1 FROM request AS sr WHERE sr.actor_id = a.actor_id "
            f"AND sr.start_utc >= ? AND sr.start_utc < ? AND {match})"
        )
        parameters.extend([start, end, f"%{term}%"])
    else:
        conditions.append("0")


@router.get("/countries")
def get_countries(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
) -> dict[str, Any]:
    """Return distinct countries with requests in the selected time range."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    database = get_database(request)
    items = database.query(
        """SELECT DISTINCT a.country AS country
           FROM actor AS a JOIN request AS r ON r.actor_id = a.actor_id
           WHERE r.start_utc >= ? AND r.start_utc < ?
             AND a.country IS NOT NULL AND TRIM(a.country) <> ''
           ORDER BY a.country""",
        [start, end],
    )
    return {"items": items, "from": start, "to": end}


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
    country_exact: bool = Query(default=False, description="Match the country exactly"),
    city: str | None = Query(default=None, min_length=1),
    asn: str | None = Query(default=None, min_length=1),
    ip: str | None = Query(default=None, min_length=1),
    ip_exact: bool = Query(default=False, description="Match the actor IP exactly"),
    search: str | None = Query(default=None, min_length=1, description="Search actor fields; qualify with field:value such as ip: or provider:"),
    global_search: str | None = Query(default=None, min_length=1, description="Search actor fields; qualify with field:value such as country: or asn:"),
    sort_by: Literal["ip", "first_time", "last_time", "provider", "asn", "city", "country", "request_count"] = Query(default="first_time"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
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
    if country is not None:
        conditions.append("a.country = ?" if country_exact else "a.country LIKE ?")
        parameters.append(country if country_exact else f"%{country}%")
    for column, value in (
        ("a.provider", provider),
        ("a.city", city),
        ("a.asn", asn),
        ("a.ip", ip),
    ):
        if value is not None:
            conditions.append(f"{column} = ?" if column == "a.ip" and ip_exact else f"{column} LIKE ?")
            parameters.append(value if column == "a.ip" and ip_exact else f"%{value}%")
    if search is not None:
        _append_actor_search(search, conditions, parameters, include_country=False, start=start, end=end)
    if global_search is not None:
        _append_actor_search(global_search, conditions, parameters, include_country=True, start=start, end=end)
    where_clause = " AND ".join(conditions)
    sort_expressions = {"ip": "a.ip", "first_time": "a.first_time", "last_time": "a.last_time", "provider": "a.provider", "asn": "a.asn", "city": "a.city", "country": "a.country", "request_count": "request_count"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, a.actor_id"
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
               ORDER BY {order_by}
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
