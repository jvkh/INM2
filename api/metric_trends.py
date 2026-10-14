"""Period-over-period trends for dashboard and list-page metric cards."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.known_hosts import known_host_match_sql
from common.search import parse_search

router = APIRouter()


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _period_metrics(database: Any, start: str, end: str, page: str, search: str | None,
                    host: str | None, host_exact: bool, country: str | None,
                    country_exact: bool, status_class: str | None,
                    burst_id: int | None, actor_ip: str | None,
                    actor_ip_exact: bool,
                    category: str | None, category_exact: bool, path: str | None,
                    path_exact: bool, known: str | None) -> dict[str, float]:
    request_conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    request_params: list[Any] = [start, end]
    if page == "actors" and country:
        request_conditions.append("a.country = ?" if country_exact else "a.country LIKE ?")
        request_params.append(country if country_exact else f"%{country}%")
    if page == "actors" and search:
        field, term = parse_search(search)
        if not term:
            request_conditions.append("0")
        elif field is None:
            request_conditions.append("(a.ip LIKE ? OR COALESCE(a.city,'') LIKE ? OR COALESCE(a.provider,'') LIKE ? OR COALESCE(a.asn,'') LIKE ?)")
            request_params.extend([f"%{term}%"] * 4)
        elif field in {"ip", "country", "city", "provider", "asn"}:
            column = {"ip": "a.ip", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn"}[field]
            request_conditions.append(f"COALESCE({column},'') LIKE ?")
            request_params.append(f"%{term}%")
        elif field == "host":
            request_conditions.append("EXISTS (SELECT 1 FROM host AS sh WHERE sh.host_id=r.host_id AND sh.name LIKE ?)")
            request_params.append(f"%{term}%")
        elif field in {"path", "category", "method", "status", "scheme", "user_agent"}:
            if field == "category":
                match = "EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id=src.category_id WHERE src.request_id=sr.request_id AND sc.category_name LIKE ?)"
            else:
                column = {"path": "request_path", "method": "request_method", "status": "downstream_status", "scheme": "request_scheme", "user_agent": "user_agent"}[field]
                match = f"COALESCE(sr.{column},'') LIKE ?"
            request_conditions.append(f"EXISTS (SELECT 1 FROM request AS sr WHERE sr.actor_id=a.actor_id AND {match})")
            request_params.append(f"%{term}%")
        else:
            request_conditions.append("0")
    if page == "hosts" and search:
        request_conditions.append("h.name LIKE ?")
        request_params.append(f"%{search}%")
    known_match = known_host_match_sql("h.name")
    if page == "hosts" and known == "own":
        request_conditions.append(known_match)
    elif page == "hosts" and known == "foreign":
        request_conditions.append(f"NOT {known_match}")
    if page == "categories" and search:
        request_conditions.append("EXISTS (SELECT 1 FROM request_category AS xrc JOIN category AS xc ON xc.category_id=xrc.category_id WHERE xrc.request_id=r.request_id AND xc.category_name LIKE ?)")
        request_params.append(f"%{search}%")
    if page == "requests":
        if search:
            field, term = parse_search(search)
            if not term:
                request_conditions.append("0")
            elif field is None:
                request_conditions.append("(a.ip LIKE ? OR COALESCE(h.name,'') LIKE ? OR COALESCE(a.country,'') LIKE ? OR COALESCE(a.city,'') LIKE ? OR COALESCE(a.provider,'') LIKE ? OR COALESCE(a.asn,'') LIKE ? OR COALESCE(r.request_path,'') LIKE ?)")
                request_params.extend([f"%{term}%"] * 7)
            elif field == "category":
                request_conditions.append("EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id=src.category_id WHERE src.request_id=r.request_id AND sc.category_name LIKE ?)")
                request_params.append(f"%{term}%")
            elif field == "status":
                request_conditions.append("CAST(r.downstream_status AS TEXT) LIKE ?")
                request_params.append(f"%{term}%")
            elif field in {"ip", "host", "country", "city", "provider", "asn", "path", "method", "scheme", "user_agent"}:
                column = {"ip": "a.ip", "host": "h.name", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn", "path": "r.request_path", "method": "r.request_method", "scheme": "r.request_scheme", "user_agent": "r.user_agent"}[field]
                request_conditions.append(f"COALESCE({column}, '') LIKE ?")
                request_params.append(f"%{term}%")
            else:
                request_conditions.append("0")
        if status_class:
            status_start = int(status_class[0]) * 100
            request_conditions.append("r.downstream_status >= ? AND r.downstream_status < ?")
            request_params.extend([status_start, status_start + 100])
        if actor_ip:
            request_conditions.append("a.ip = ?" if actor_ip_exact else "a.ip LIKE ?")
            request_params.append(actor_ip if actor_ip_exact else f"%{actor_ip}%")
        if host:
            request_conditions.append("h.name = ?" if host_exact else "h.name LIKE ?")
            request_params.append(host if host_exact else f"%{host}%")
        if category:
            request_conditions.append("EXISTS (SELECT 1 FROM request_category AS xrc JOIN category AS xc ON xc.category_id=xrc.category_id WHERE xrc.request_id=r.request_id AND xc.category_name = ?)" if category_exact else "EXISTS (SELECT 1 FROM request_category AS xrc JOIN category AS xc ON xc.category_id=xrc.category_id WHERE xrc.request_id=r.request_id AND xc.category_name LIKE ?)")
            request_params.append(category if category_exact else f"%{category}%")
        if path:
            request_conditions.append("r.request_path = ?" if path_exact else "r.request_path LIKE ?")
            request_params.append(path if path_exact else f"%{path}%")
        if burst_id:
            request_conditions.append("EXISTS (SELECT 1 FROM burst_request AS xb WHERE xb.burst_id=? AND xb.request_id=r.request_id)")
            request_params.append(burst_id)

    burst_conditions = ["b.start_time >= ?", "b.start_time < ?"]
    burst_params: list[Any] = [start, end]
    if page == "bursts":
        if host:
            burst_conditions.append("h.name = ?" if host_exact else "h.name LIKE ?")
            burst_params.append(host if host_exact else f"%{host}%")
        if known == "own":
            burst_conditions.append(known_match)
        elif known == "foreign":
            burst_conditions.append(f"NOT {known_match}")
        if country:
            burst_conditions.append("a.country = ?" if country_exact else "a.country LIKE ?")
            burst_params.append(country if country_exact else f"%{country}%")
        if search:
            field, term = parse_search(search)
            if not term:
                burst_conditions.append("0")
            elif field is None:
                burst_conditions.append("(CAST(b.burst_id AS TEXT) LIKE ? OR a.ip LIKE ? OR COALESCE(a.provider,'') LIKE ? OR COALESCE(a.asn,'') LIKE ? OR COALESCE(a.city,'') LIKE ?)")
                burst_params.extend([f"%{term}%"] * 5)
            elif field in {"ip", "host", "country", "city", "provider", "asn"}:
                column = {"ip": "a.ip", "host": "h.name", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn"}[field]
                burst_conditions.append(f"COALESCE({column},'') LIKE ?")
                burst_params.append(f"%{term}%")
            else:
                burst_conditions.append("0")

    sql = f"""WITH filtered_requests AS (
            SELECT r.*, a.country, a.first_time, a.ip, a.city, a.provider, a.asn, h.name AS host_name
            FROM request AS r JOIN actor AS a ON a.actor_id=r.actor_id
            LEFT JOIN host AS h ON h.host_id=r.host_id
            WHERE {' AND '.join(request_conditions)}
        ), filtered_bursts AS (
            SELECT b.* FROM burst AS b JOIN actor AS a ON a.actor_id=b.actor_id
            LEFT JOIN host AS h ON h.host_id=b.host_id
            WHERE {' AND '.join(burst_conditions)}
        ), category_traffic AS (
            SELECT c.category_id, COUNT(DISTINCT fr.request_id) AS request_count
            FROM filtered_requests AS fr JOIN request_category AS rc ON rc.request_id=fr.request_id
            JOIN category AS c ON c.category_id=rc.category_id GROUP BY c.category_id
        ), host_traffic AS (
            SELECT host_id, COUNT(*) AS request_count FROM filtered_requests
            WHERE host_id IS NOT NULL GROUP BY host_id
        )
        SELECT
            (SELECT COUNT(*) FROM filtered_requests) AS request_count,
            (SELECT COUNT(*) FROM filtered_requests WHERE downstream_status >= 400) AS error_request_count,
            (SELECT COUNT(*) FROM filtered_requests WHERE UPPER(COALESCE(request_method,'')) IN ('POST','PUT','PATCH','DELETE')) AS write_request_count,
            (SELECT COUNT(DISTINCT actor_id) FROM filtered_requests) AS actor_count,
            (SELECT COUNT(DISTINCT actor_id) FROM filtered_requests WHERE first_time >= ? AND first_time < ?) AS new_actor_count,
            (SELECT COUNT(DISTINCT country) FROM filtered_requests WHERE country IS NOT NULL AND country != '') AS country_count,
            (SELECT COUNT(DISTINCT host_id) FROM filtered_requests WHERE host_id IS NOT NULL) AS host_count,
            (SELECT COUNT(*) FROM category_traffic) AS category_count,
            COALESCE((SELECT MAX(request_count) FROM host_traffic), 0) AS top_host_request_count,
            COALESCE((SELECT MAX(request_count) FROM category_traffic), 0) AS top_category_request_count,
            COALESCE(100.0 * (SELECT COUNT(*) FROM filtered_requests WHERE LOWER(COALESCE(request_scheme,''))='https') / NULLIF((SELECT COUNT(*) FROM filtered_requests),0), 0) AS https_share,
            (SELECT COUNT(*) FROM filtered_bursts) AS burst_count,
            (SELECT COUNT(DISTINCT actor_id) FROM filtered_bursts) AS burst_actor_count,
            COALESCE((SELECT SUM(read_count+write_count+other_count) FROM filtered_bursts),0) AS burst_request_count,
            COALESCE((SELECT AVG((julianday(end_time)-julianday(start_time))*86400.0) FROM filtered_bursts),0) AS avg_burst_duration,
            COALESCE((SELECT CAST(COUNT(*) AS REAL)/NULLIF(COUNT(DISTINCT actor_id),0) FROM filtered_requests),0) AS avg_requests_per_actor
    """
    row = database.query(sql, [*request_params, *burst_params, start, end])[0]
    return {key: float(value or 0) for key, value in row.items()}


@router.get("/metric_trends")
def get_metric_trends(
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    page: Literal["dashboard", "bursts", "actors", "hosts", "categories", "requests"] = Query(default="dashboard"),
    search: str | None = Query(default=None, min_length=1),
    host: str | None = Query(default=None, min_length=1),
    host_exact: bool = Query(default=False),
    country: str | None = Query(default=None, min_length=1),
    country_exact: bool = Query(default=False),
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = Query(default=None),
    burst_id: int | None = Query(default=None, ge=1),
    actor_ip: str | None = Query(default=None, min_length=1),
    actor_ip_exact: bool = Query(default=False),
    category: str | None = Query(default=None, min_length=1),
    category_exact: bool = Query(default=False),
    path: str | None = Query(default=None, min_length=1),
    path_exact: bool = Query(default=False),
    known: Literal["own", "foreign"] | None = Query(default=None),
) -> dict[str, Any]:
    """Return values for the selected range and its immediately preceding equal-length range."""
    start_dt = from_ if from_.tzinfo else from_.replace(tzinfo=timezone.utc)
    end_dt = to if to.tzinfo else to.replace(tzinfo=timezone.utc)
    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    previous_start = start_dt - (end_dt - start_dt)
    current_start, current_end = _utc_text(start_dt), _utc_text(end_dt)
    previous_start_text, previous_end_text = _utc_text(previous_start), current_start
    database = get_database(request)
    previous = _period_metrics(database, previous_start_text, previous_end_text, page, search, host, host_exact, country, country_exact, status_class, burst_id, actor_ip, actor_ip_exact, category, category_exact, path, path_exact, known)
    current = _period_metrics(database, current_start, current_end, page, search, host, host_exact, country, country_exact, status_class, burst_id, actor_ip, actor_ip_exact, category, category_exact, path, path_exact, known)
    keys = current.keys()
    result = {}
    for key in keys:
        current_value, previous_value = current[key], previous[key]
        change = ((current_value - previous_value) / previous_value * 100) if previous_value else 0.0
        direction = "steady" if current_value == 0 and previous_value == 0 or abs(change) <= 5 else "up" if change > 0 else "down"
        result[key] = {"current": current_value, "previous": previous_value, "change_percent": change, "direction": direction}
    return {"from": current_start, "to": current_end, "previous_from": previous_start_text,
            "previous_to": previous_end_text, "metrics": result}
