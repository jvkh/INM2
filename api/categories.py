"""Request counts grouped by category."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.search import parse_search


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

    parameters: list[Any] = [start, end]

    having_clause = ""
    having_parameters: list[Any] = []
    if category is not None:
        field, term = parse_search(category)
        pattern = f"%{term.replace('%', '')}%"
        read_expr = "CAST(SUM(CASE WHEN UPPER(COALESCE(r.request_method, '')) IN ('GET', 'HEAD', 'OPTIONS') THEN 1 ELSE 0 END) AS TEXT)"
        write_expr = "CAST(SUM(CASE WHEN UPPER(COALESCE(r.request_method, '')) IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS TEXT)"
        other_expr = "CAST(SUM(CASE WHEN r.request_id IS NOT NULL AND UPPER(COALESCE(r.request_method, '')) NOT IN ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS TEXT)"
        http_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'http' THEN 1 ELSE 0 END) AS TEXT)"
        https_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) AS TEXT)"
        other_scheme_expr = "CAST(SUM(CASE WHEN r.request_id IS NOT NULL AND LOWER(COALESCE(r.request_scheme, '')) NOT IN ('http', 'https') THEN 1 ELSE 0 END) AS TEXT)"
        database = get_database(request)
        denominator = database.query("SELECT COUNT(*) AS total FROM request AS r WHERE r.start_utc >= ? AND r.start_utc < ?", (start, end))[0]["total"]
        traffic_share_expr = f"CAST(COUNT(r.request_id) * 100.0 / {denominator or 1} AS TEXT)"
        https_share_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(r.request_id), 0) AS TEXT)"
        expressions = {
            "category": ["c.category_name"], "requests": ["CAST(COUNT(r.request_id) AS TEXT)"],
            "read_count": [read_expr], "write_count": [write_expr], "other_count": [other_expr],
            "http_count": [http_expr], "https_count": [https_expr],
            "scheme": [https_share_expr], "traffic_share": [traffic_share_expr], "https_share": [https_share_expr],
        }
        chosen = (["c.category_name", "CAST(COUNT(r.request_id) AS TEXT)", read_expr, write_expr, other_expr, http_expr, https_expr, other_scheme_expr, traffic_share_expr, https_share_expr]
                 if field is None else expressions.get(field, []))
        if term and chosen:
            having_clause = "HAVING (" + " OR ".join(f"{expr} LIKE ?" for expr in chosen) + ")"
            having_parameters = [pattern] * len(chosen)
        else:
            having_clause = "HAVING 0"
    database = get_database(request)
    sort_expressions = {"category_name": "c.category_name", "total_count": "total_count", "read_count": "read_count", "write_count": "write_count", "other_count": "other_count", "http_count": "http_count", "https_count": "https_count", "other_scheme_count": "other_scheme_count", "traffic_share": "total_count", "https_share": "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0)"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, c.category_name ASC, c.category_id"
    items = database.query(
        f"""SELECT c.category_id, c.category_name,
                   COUNT(r.request_id) AS total_count,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 IN ('GET', 'HEAD', 'OPTIONS') THEN 1 ELSE 0 END) AS read_count,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS write_count,
                   SUM(CASE WHEN r.request_id IS NOT NULL
                                 AND UPPER(COALESCE(r.request_method, ''))
                                 NOT IN ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE')
                            THEN 1 ELSE 0 END) AS other_count,
                   SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'http'
                            THEN 1 ELSE 0 END) AS http_count,
                   SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https'
                            THEN 1 ELSE 0 END) AS https_count,
                   SUM(CASE WHEN r.request_id IS NOT NULL
                                 AND LOWER(COALESCE(r.request_scheme, ''))
                                 NOT IN ('http', 'https')
                            THEN 1 ELSE 0 END) AS other_scheme_count
            FROM category AS c
            LEFT JOIN request_category AS rc ON rc.category_id = c.category_id
            LEFT JOIN request AS r ON r.request_id = rc.request_id
                                   AND r.start_utc >= ? AND r.start_utc < ?
            GROUP BY c.category_id, c.category_name
            {having_clause}
            ORDER BY {order_by}""",
        [*parameters, *having_parameters],
    )
    request_conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    request_parameters: list[Any] = [start, end]
    matching_category_ids = [item["category_id"] for item in items]
    if category is not None:
        if matching_category_ids:
            placeholders = ", ".join("?" for _ in matching_category_ids)
            request_conditions.append(f"EXISTS (SELECT 1 FROM request_category AS rc WHERE rc.request_id = r.request_id AND rc.category_id IN ({placeholders}))")
            request_parameters.extend(matching_category_ids)
        else:
            request_conditions.append("0")
    else:
        request_conditions.append("EXISTS (SELECT 1 FROM request_category AS rc WHERE rc.request_id = r.request_id)")
    summary = database.query(
        f"""SELECT COUNT(*) AS request_count,
                   COALESCE(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END), 0) AS https_count
            FROM request AS r
            WHERE {' AND '.join(request_conditions)}""",
        request_parameters,
    )[0]
    return {"items": items, "total": len(items), "summary": summary, "from": start, "to": end, "category": category}
