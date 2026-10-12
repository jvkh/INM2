"""Request listing endpoint and its optional filters."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from api.dependencies import get_database

router = APIRouter()


def _utc_timestamp(value: datetime) -> str:
    """Normalize timestamps to the UTC format stored by the collector."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/requests/{id}")
def get_request(
    request: Request,
    id: int = Path(ge=1, description="Request ID"),
) -> dict[str, Any]:
    """Return one request with its actor, host, and categories."""
    database = get_database(request)
    rows = database.query(
        """SELECT r.*, a.ip AS actor_ip, a.first_time AS actor_first_time,
                  a.last_time AS actor_last_time, a.provider, a.asn, a.city, a.country,
                  h.name AS host
           FROM request AS r
           JOIN actor AS a ON a.actor_id = r.actor_id
           LEFT JOIN host AS h ON h.host_id = r.host_id
           WHERE r.request_id = ?""",
        (id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Request not found")

    result = rows[0]
    category_rows = database.query(
        """SELECT c.category_name
           FROM request_category AS rc
           JOIN category AS c ON c.category_id = rc.category_id
           WHERE rc.request_id = ?
           ORDER BY c.category_name""",
        (id,),
    )
    result["categories"] = [row["category_name"] for row in category_rows]
    return result


@router.get("/requests")
def get_requests(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    host: str | None = Query(default=None, min_length=1),
    actor: str | None = Query(default=None, min_length=1, description="Actor IP address"),
    ip: str | None = Query(default=None, min_length=1, description="Actor IP address"),
    actor_id: int | None = Query(default=None, ge=1),
    country: str | None = Query(default=None, min_length=1),
    city: str | None = Query(default=None, min_length=1),
    provider: str | None = Query(default=None, min_length=1),
    asn: str | None = Query(default=None, min_length=1),
    category: str | None = Query(default=None, min_length=1, description="Category-name substring"),
    search: str | None = Query(default=None, min_length=1, description="Search IP, country, city, provider, ASN, or request path"),
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = Query(default=None),
    burst_id: int | None = Query(default=None, ge=1, description="Return requests associated with this burst"),
    sort_by: Literal["start_utc", "request_method", "request_path", "downstream_status", "actor_ip", "host", "duration", "downstream_content_size"] = Query(default="start_utc"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return requests matching all supplied filters within a time range."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    parameters: list[Any] = [start, end]
    if burst_id is not None:
        conditions.append(
            """EXISTS (
                   SELECT 1 FROM burst AS b
                   WHERE b.burst_id = ?
                     AND b.actor_id = r.actor_id
                     AND b.host_id IS r.host_id
                     AND r.start_utc >= b.start_time
                     AND r.start_utc <= b.end_time
               )"""
        )
        parameters.append(burst_id)
    if category is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name LIKE ?)"
        )
        parameters.append(f"%{category}%")
    for column, value in (
        ("h.name", host),
        ("a.ip", actor),
        ("a.ip", ip),
        ("a.actor_id", actor_id),
        ("a.country", country),
        ("a.city", city),
        ("a.provider", provider),
        ("a.asn", asn),
    ):
        if value is not None:
            if column == "a.actor_id":
                conditions.append(f"{column} = ?")
                parameters.append(value)
            else:
                conditions.append(f"{column} LIKE ?")
                parameters.append(f"%{value}%")
    if search is not None:
        conditions.append("(a.ip LIKE ? OR a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ? OR r.request_path LIKE ?)")
        parameters.extend([f"%{search}%"] * 6)
    if status_class is not None:
        status_start = int(status_class[0]) * 100
        conditions.append("r.downstream_status >= ? AND r.downstream_status < ?")
        parameters.extend([status_start, status_start + 100])

    where_clause = " AND ".join(conditions)
    database = get_database(request)
    joins = """FROM request AS r
               JOIN actor AS a ON a.actor_id = r.actor_id
               LEFT JOIN host AS h ON h.host_id = r.host_id"""
    sort_expressions = {"start_utc": "r.start_utc", "request_method": "r.request_method", "request_path": "r.request_path", "downstream_status": "r.downstream_status", "actor_ip": "a.ip", "host": "h.name", "duration": "r.duration", "downstream_content_size": "r.downstream_content_size"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, r.start_utc DESC, r.request_id DESC"
    total_rows = database.query(
        f"SELECT COUNT(*) AS total {joins} WHERE {where_clause}", parameters
    )
    items = database.query(
        f"""SELECT r.request_id, r.start_utc, r.actor_id, a.ip AS actor_ip,
                      a.provider, a.country, a.city, a.asn, r.host_id, h.name AS host,
                      r.request_method, r.request_path, r.request_scheme,
                      (SELECT GROUP_CONCAT(c.category_name, ', ')
                       FROM request_category AS rc
                       JOIN category AS c ON c.category_id = rc.category_id
                       WHERE rc.request_id = r.request_id) AS categories,
                      r.downstream_status, r.downstream_content_size,
                      r.duration, r.user_agent
               {joins}
               WHERE {where_clause}
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
    }
