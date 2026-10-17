"""Request counts grouped by host."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.known_hosts import known_host_match_sql
from common.search import parse_search


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
    known: Literal["own", "foreign"] | None = Query(default=None, description="Limit to configured or foreign hosts"),
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
    known_match = known_host_match_sql("h.name")
    if known == "own":
        conditions.append(known_match)
    elif known == "foreign":
        conditions.append(f"NOT {known_match}")

    having_clause = ""
    having_parameters: list[Any] = []
    if host is not None:
        field, term = parse_search(host)
        if not term:
            having_clause = "HAVING 0"
            field = None
        pattern = f"%{term}%"
        read_expr = "CAST(SUM(CASE WHEN UPPER(COALESCE(r.request_method, '')) IN ('GET', 'HEAD', 'OPTIONS') THEN 1 ELSE 0 END) AS TEXT)"
        write_expr = "CAST(SUM(CASE WHEN UPPER(COALESCE(r.request_method, '')) IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS TEXT)"
        other_expr = "CAST(SUM(CASE WHEN UPPER(COALESCE(r.request_method, '')) NOT IN ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS TEXT)"
        http_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'http' THEN 1 ELSE 0 END) AS TEXT)"
        https_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) AS TEXT)"
        other_scheme_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) NOT IN ('http', 'https') THEN 1 ELSE 0 END) AS TEXT)"
        share_expr = "CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0) AS TEXT)"
        expressions = {
            "host": ["h.name"], "requests": ["CAST(COUNT(*) AS TEXT)"],
            "read_count": [read_expr], "write_count": [write_expr], "other_count": [other_expr],
            "http_count": [http_expr], "https_count": [https_expr], "scheme": [http_expr, https_expr], "https_share": [share_expr],
        }
        chosen = (["h.name", "CAST(COUNT(*) AS TEXT)", read_expr, write_expr, other_expr, http_expr, https_expr, other_scheme_expr, share_expr]
                 if field is None else expressions.get(field, []))
        if term and chosen:
            having_clause = "HAVING (" + " OR ".join(f"{expr} LIKE ?" for expr in chosen) + ")"
            having_parameters = [pattern] * len(chosen)
        else:
            having_clause = "HAVING 0"
    database = get_database(request)
    sort_expressions = {"host": "h.name", "total_count": "total_count", "read_count": "read_count", "write_count": "write_count", "other_count": "other_count", "http_count": "http_count", "https_count": "https_count", "other_scheme_count": "other_scheme_count", "https_share": "(CAST(SUM(CASE WHEN LOWER(COALESCE(r.request_scheme, '')) = 'https' THEN 1 ELSE 0 END) AS REAL) / NULLIF(COUNT(*), 0))"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, h.name ASC, h.host_id"
    items = database.query(
        f"""SELECT h.host_id, h.name AS host,
                   CASE WHEN {known_match} THEN 1 ELSE 0 END AS known,
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
            {having_clause}
            ORDER BY {order_by}""",
        [*parameters, *having_parameters],
    )
    known_count = database.query("SELECT COUNT(*) AS count FROM known_host")[0]["count"]
    return {"items": items, "total": len(items), "known_count": known_count, "from": start, "to": end, "host": host, "known": known}
