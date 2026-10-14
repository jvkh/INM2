"""Request counts grouped by category."""

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


@router.get("/categories")
def get_categories(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    category: str | None = Query(default=None, min_length=1, description="Category-name substring"),
    sort_by: Literal["category_name", "total_count", "read_count", "write_count", "other_count", "http_count", "https_count", "other_scheme_count", "traffic_share", "https_share"] = Query(default="category_name"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
) -> dict[str, Any]:
    """Return request-method and HTTP-scheme counts for matching categories."""
    start = _utc_text(from_)
    end = _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    parameters: list[Any] = [start, end]
    if category is not None:
        conditions.append("c.category_name LIKE ?")
        parameters.append(f"%{category}%")

    database = get_database(request)
    sort_expressions = {"category_name": "c.category_name", "total_count": "total_count", "read_count": "read_count", "write_count": "write_count", "other_count": "other_count", "http_count": "http_count", "https_count": "https_count", "other_scheme_count": "other_scheme_count", "traffic_share": "total_count", "https_share": "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0)"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, c.category_name ASC, c.category_id"
    items = database.query(
        f"""SELECT c.category_id, c.category_name,
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
            JOIN request_category AS rc ON rc.request_id = r.request_id
            JOIN category AS c ON c.category_id = rc.category_id
            WHERE {' AND '.join(conditions)}
            GROUP BY c.category_id, c.category_name
            ORDER BY {order_by}""",
        parameters,
    )
    request_conditions = ["r.start_utc >= ?", "r.start_utc < ?", "EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id" + (" AND c.category_name LIKE ?" if category is not None else "") + ")"]
    request_parameters: list[Any] = [start, end]
    if category is not None:
        request_parameters.append(f"%{category}%")
    summary = database.query(
        f"""SELECT COUNT(*) AS request_count,
                   COALESCE(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END), 0) AS https_count
            FROM request AS r
            WHERE {' AND '.join(request_conditions)}""",
        request_parameters,
    )[0]
    return {"items": items, "total": len(items), "summary": summary, "from": start, "to": end, "category": category}
