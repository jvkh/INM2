"""Request listing endpoint and its optional filters."""

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
                  h.name AS host,
                  CASE WHEN EXISTS (SELECT 1 FROM known_host AS kh WHERE kh.name = CASE WHEN lower(rtrim(h.name, '.')) LIKE 'www.%' THEN substr(lower(rtrim(h.name, '.')), 5) ELSE lower(rtrim(h.name, '.')) END) THEN 1 ELSE 0 END AS host_known
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
    host_exact: bool = Query(default=False, description="Match the host exactly"),
    actor: str | None = Query(default=None, min_length=1, description="Actor IP address"),
    actor_exact: bool = Query(default=False, description="Match the actor IP exactly"),
    ip: str | None = Query(default=None, min_length=1, description="Actor IP address"),
    actor_id: int | None = Query(default=None, ge=1),
    country: str | None = Query(default=None, min_length=1),
    city: str | None = Query(default=None, min_length=1),
    provider: str | None = Query(default=None, min_length=1),
    asn: str | None = Query(default=None, min_length=1),
    category: str | None = Query(default=None, min_length=1, description="Category-name substring"),
    category_exact: bool = Query(default=False, description="Match the category name exactly"),
    path: str | None = Query(default=None, min_length=1, description="Request-path substring"),
    path_exact: bool = Query(default=False, description="Match the request path exactly"),
    search: str | None = Query(default=None, min_length=1, description="Search across request fields; qualify with field:value such as host:example.org or pfad:/login"),
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = Query(default=None),
    burst_id: int | None = Query(default=None, ge=1, description="Return requests associated with this burst"),
    sort_by: Literal["start_utc", "request_method", "request_path", "user_agent", "downstream_status", "actor_ip", "host", "duration", "downstream_content_size"] = Query(default="start_utc"),
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
            "EXISTS (SELECT 1 FROM burst_request AS br WHERE br.burst_id = ? AND br.request_id = r.request_id)"
        )
        parameters.append(burst_id)
    if category is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name = ?)" if category_exact else
            "EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name LIKE ?)"
        )
        parameters.append(category if category_exact else f"%{category}%")
    if path is not None:
        conditions.append("r.request_path = ?" if path_exact else "r.request_path LIKE ?")
        parameters.append(path if path_exact else f"%{path}%")
    for column, value, exact in (
        ("h.name", host, host_exact),
        ("a.ip", actor, actor_exact),
        ("a.ip", ip, False),
        ("a.actor_id", actor_id, True),
        ("a.country", country, False),
        ("a.city", city, False),
        ("a.provider", provider, False),
        ("a.asn", asn, False),
    ):
        if value is not None:
            if exact:
                conditions.append(f"{column} = ?")
                parameters.append(value)
            else:
                conditions.append(f"{column} LIKE ?")
                parameters.append(f"%{value}%")
    if search is not None:
        field, term = parse_search(search)
        if not term:
            conditions.append("0")
        elif field is None:
            conditions.append("(a.ip LIKE ? OR h.name LIKE ? OR a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ? OR r.request_path LIKE ?)")
            parameters.extend([f"%{term}%"] * 7)
        elif field == "category":
            conditions.append("EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id = src.category_id WHERE src.request_id = r.request_id AND sc.category_name LIKE ?)")
            parameters.append(f"%{term}%")
        elif field == "status":
            conditions.append("CAST(r.downstream_status AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field in {"ip", "host", "country", "city", "provider", "asn", "path", "method", "scheme", "user_agent"}:
            column = {"ip": "a.ip", "host": "h.name", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn", "path": "r.request_path", "method": "r.request_method", "scheme": "r.request_scheme", "user_agent": "r.user_agent"}[field]
            conditions.append(f"{column} LIKE ?")
            parameters.append(f"%{term}%")
        else:
            conditions.append("0")
    if status_class is not None:
        status_start = int(status_class[0]) * 100
        conditions.append("r.downstream_status >= ? AND r.downstream_status < ?")
        parameters.extend([status_start, status_start + 100])

    where_clause = " AND ".join(conditions)
    database = get_database(request)
    joins = """FROM request AS r
               JOIN actor AS a ON a.actor_id = r.actor_id
               LEFT JOIN host AS h ON h.host_id = r.host_id"""
    sort_expressions = {"start_utc": "r.start_utc", "request_method": "r.request_method", "request_path": "r.request_path", "user_agent": "r.user_agent", "downstream_status": "r.downstream_status", "actor_ip": "a.ip", "host": "h.name", "duration": "r.duration", "downstream_content_size": "r.downstream_content_size"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, r.start_utc DESC, r.request_id DESC"
    total_rows = database.query(
        f"SELECT COUNT(*) AS total {joins} WHERE {where_clause}", parameters
    )
    items = database.query(
        f"""SELECT r.request_id, r.start_utc, r.actor_id, a.ip AS actor_ip,
                      a.provider, a.country, a.city, a.asn, r.host_id, h.name AS host,
                      CASE WHEN EXISTS (SELECT 1 FROM known_host AS kh WHERE kh.name = CASE WHEN lower(rtrim(h.name, '.')) LIKE 'www.%' THEN substr(lower(rtrim(h.name, '.')), 5) ELSE lower(rtrim(h.name, '.')) END) THEN 1 ELSE 0 END AS host_known,
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
