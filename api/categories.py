"""Request counts grouped by category."""

from datetime import datetime, timezone
from typing import Any

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
            ORDER BY c.category_name""",
        parameters,
    )
    return {"items": items, "from": start, "to": end, "category": category}
