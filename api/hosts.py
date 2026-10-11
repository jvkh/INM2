"""Request counts grouped by host."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database


router = APIRouter()


def _utc_text(value: datetime) -> str:
    """Normalize a query timestamp to the collector's UTC format."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/hosts")
def get_hosts(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    host: str | None = Query(default=None, min_length=1, description="Host-name substring"),
    sort_by: Literal["host", "total_count", "read_count", "write_count", "other_count", "http_count", "https_count", "other_scheme_count", "https_share"] = Query(default="total_count"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> dict[str, Any]:
    """Return request-method and HTTP-scheme counts grouped by host."""
    start = _utc_text(from_)
    end = _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    parameters: list[Any] = [start, end]
    if host is not None:
        conditions.append("h.name LIKE ?")
        parameters.append(f"%{host}%")

    database = get_database(request)
    sort_expressions = {"host": "h.name", "total_count": "total_count", "read_count": "read_count", "write_count": "write_count", "other_count": "other_count", "http_count": "http_count", "https_count": "https_count", "other_scheme_count": "other_scheme_count", "https_share": "(CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0))"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, h.name ASC, h.host_id"
    items = database.query(
        f"""SELECT h.host_id, h.name AS host,
                   COUNT(*) AS total_count,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 IN ('GET', 'HEAD', 'OPTIONS') THEN 1 ELSE 0 END) AS read_count,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS write_count,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 NOT IN ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE')
                            THEN 1 ELSE 0 END) AS other_count,
                   SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'http'
                            THEN 1 ELSE 0 END) AS http_count,
                   SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https'
                            THEN 1 ELSE 0 END) AS https_count,
                   SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, ''))
                                 NOT IN ('http', 'https')
                            THEN 1 ELSE 0 END) AS other_scheme_count
            FROM request AS r
            JOIN host AS h ON h.host_id = r.host_id
            WHERE {' AND '.join(conditions)}
            GROUP BY h.host_id, h.name
            ORDER BY {order_by}""",
        parameters,
    )
    return {"items": items, "total": len(items), "from": start, "to": end, "host": host}
