"""Request listing endpoint and its optional filters."""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request

from api.dependencies import get_database
from common.known_hosts import known_host_match_sql
from common.incidents import incident_request_condition, incident_request_parameters
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
        f"""SELECT r.*, a.ip AS actor_ip, a.first_time AS actor_first_time,
                  a.last_time AS actor_last_time, a.provider, a.asn, a.city, a.country,
                  h.name AS host,
                  CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS host_known
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
    incident_id: int | None = Query(default=None, ge=1, description="Requests belonging to an incident"),
    country: str | None = Query(default=None, min_length=1),
    country_exact: bool = Query(default=False, description="Match the country name exactly"),
    city: str | None = Query(default=None, min_length=1),
    provider: str | None = Query(default=None, min_length=1),
    provider_exact: bool = Query(default=False, description="Match the provider name exactly"),
    asn: str | None = Query(default=None, min_length=1),
    category: str | None = Query(default=None, min_length=1, description="Category-name substring"),
    category_exact: bool = Query(default=False, description="Match the category name exactly"),
    request_class: Literal["read", "write", "other"] | None = Query(default=None, description="Limit to read, write, or other request methods"),
    path: str | None = Query(default=None, min_length=1, description="Request-path substring"),
    path_exact: bool = Query(default=False, description="Match the request path exactly"),
    search: str | None = Query(default=None, min_length=1, description="Search across request fields; qualify with field:value such as host:example.org or pfad:/login"),
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = Query(default=None),
    burst_id: int | None = Query(default=None, ge=1, description="Return requests associated with this burst"),
    burst_extreme: Literal["min_requests", "max_requests", "min_duration", "max_duration"] | None = Query(default=None, description="Return requests belonging to bursts with the selected period minimum or maximum"),
    without_burst: bool = Query(default=False, description="Return only requests that are not assigned to a burst"),
    group_actor_id: int | None = Query(default=None, ge=1, description="Actor ID for a grouped-request detail view"),
    group_host_id: int | None = Query(default=None, ge=0, description="Host ID for a grouped-request detail view; 0 means no host"),
    sort_by: Literal["start_utc", "request_method", "request_path", "user_agent", "downstream_status", "actor_ip", "host", "duration", "downstream_content_size", "request_content_size", "burst_id"] = Query(default="start_utc"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    all_results: bool = Query(default=False, description="Return every matching row for expandable detail tables"),
) -> dict[str, Any]:
    """Return requests matching all supplied filters within a time range."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    parameters: list[Any] = [start, end]
    if group_actor_id is not None and group_host_id is not None:
        conditions.append("r.actor_id = ? AND r.host_id IS ?")
        parameters.extend([group_actor_id, group_host_id or None])
    if incident_id is not None:
        conditions.append(incident_request_condition())
        parameters.extend(incident_request_parameters(incident_id))
    if burst_id is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM burst_request AS br WHERE br.burst_id = ? AND br.request_id = r.request_id)"
        )
        parameters.append(burst_id)
    if burst_extreme is not None:
        if burst_extreme.endswith("requests"):
            outer_value, inner_value = "be.read_count + be.write_count + be.other_count", "read_count + write_count + other_count"
        else:
            outer_value = "(julianday(be.end_time) - julianday(be.start_time))"
            inner_value = "(julianday(end_time) - julianday(start_time))"
        aggregate = "MIN" if burst_extreme.startswith("min_") else "MAX"
        conditions.append(
            f"""EXISTS (
                SELECT 1 FROM burst_request AS bre
                JOIN burst AS be ON be.burst_id = bre.burst_id
                WHERE bre.request_id = r.request_id
                  AND be.start_time >= ? AND be.start_time < ?
                  AND {outer_value} = (
                      SELECT {aggregate}({inner_value}) FROM burst
                      WHERE start_time >= ? AND start_time < ?
                  )
            )"""
        )
        parameters.extend([start, end, start, end])
    if without_burst:
        conditions.append("NOT EXISTS (SELECT 1 FROM burst_request AS br WHERE br.request_id = r.request_id)")
    if category is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name = ?)" if category_exact else
            "EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name LIKE ?)"
        )
        parameters.append(category if category_exact else f"%{category}%")
    if request_class is not None:
        method = "UPPER(COALESCE(r.request_method, ''))"
        if request_class == "read":
            conditions.append(f"{method} IN ('GET', 'HEAD', 'OPTIONS')")
        elif request_class == "write":
            conditions.append(f"{method} IN ('POST', 'PUT', 'PATCH', 'DELETE')")
        else:
            conditions.append(f"{method} NOT IN ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE')")
    if path is not None:
        conditions.append("r.request_path = ?" if path_exact else "r.request_path LIKE ?")
        parameters.append(path if path_exact else f"%{path}%")
    for column, value, exact in (
        ("h.name", host, host_exact),
        ("a.ip", actor, actor_exact),
        ("a.ip", ip, False),
        ("a.actor_id", actor_id, True),
        ("a.country", country, country_exact),
        ("a.city", city, False),
        ("a.provider", provider, provider_exact),
        ("a.asn", asn, False),
    ):
        if value is not None:
            if exact:
                conditions.append(f"TRIM({column}) = ?" if column in {"a.country", "a.provider"} else f"{column} = ?")
                parameters.append(value)
            else:
                conditions.append(f"{column} LIKE ?")
                parameters.append(f"%{value}%")
    if search is not None:
        field, term = parse_search(search)
        if not term:
            conditions.append("0")
        elif field is None:
            conditions.append("(a.ip LIKE ? OR h.name LIKE ? OR a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ? OR r.request_path LIKE ? OR r.request_method LIKE ? OR r.request_scheme LIKE ? OR CAST(r.downstream_status AS TEXT) LIKE ? OR COALESCE(r.user_agent, '') LIKE ? OR r.start_utc LIKE ? OR CAST(r.duration AS TEXT) LIKE ? OR CAST(r.downstream_content_size AS TEXT) LIKE ? OR CAST(r.request_content_size AS TEXT) LIKE ? OR CAST((SELECT br.burst_id FROM burst_request AS br WHERE br.request_id = r.request_id LIMIT 1) AS TEXT) LIKE ? OR EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id = src.category_id WHERE src.request_id = r.request_id AND sc.category_name LIKE ?))")
            parameters.extend([f"%{term}%"] * 17)
        elif field == "burst_id":
            conditions.append("CAST((SELECT br.burst_id FROM burst_request AS br WHERE br.request_id = r.request_id LIMIT 1) AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "incident_id":
            conditions.append(incident_request_condition())
            parameters.extend(incident_request_parameters(int(term)) if term.isdigit() else [0])
        elif field == "location":
            conditions.append("(a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ?)")
            parameters.extend([f"%{term}%"] * 4)
        elif field == "actor":
            conditions.append("(a.ip LIKE ? OR COALESCE(a.country,'') LIKE ? OR COALESCE(a.city,'') LIKE ? OR COALESCE(a.provider,'') LIKE ? OR COALESCE(a.asn,'') LIKE ?)")
            parameters.extend([f"%{term}%"] * 5)
        elif field == "time":
            conditions.append("r.start_utc LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "duration":
            conditions.append("CAST(r.duration AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "response_size":
            conditions.append("CAST(r.downstream_content_size AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "request_body_size":
            conditions.append("CAST(r.request_content_size AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
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
    sort_expressions = {"start_utc": "r.start_utc", "request_method": "r.request_method", "request_path": "r.request_path", "user_agent": "r.user_agent", "downstream_status": "r.downstream_status", "actor_ip": "a.ip", "host": "h.name", "duration": "r.duration", "downstream_content_size": "r.downstream_content_size", "request_content_size": "r.request_content_size", "burst_id": "(SELECT br.burst_id FROM burst_request AS br WHERE br.request_id = r.request_id LIMIT 1)"}
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, r.start_utc DESC, r.request_id DESC"
    total_rows = database.query(
        f"SELECT COUNT(*) AS total {joins} WHERE {where_clause}", parameters
    )
    extreme_summary: dict[str, Any] = {}
    if burst_extreme is not None:
        if burst_extreme.endswith("requests"):
            burst_value = "read_count + write_count + other_count"
        else:
            burst_value = "(julianday(end_time) - julianday(start_time)) * 86400.0"
        aggregate = "MIN" if burst_extreme.startswith("min_") else "MAX"
        summary = database.query(
            f"""SELECT COUNT(*) AS matching_burst_count, MIN({burst_value}) AS burst_extreme_value
                FROM burst WHERE start_time >= ? AND start_time < ?
                  AND {burst_value} = (SELECT {aggregate}({burst_value}) FROM burst WHERE start_time >= ? AND start_time < ?)""",
            (start, end, start, end),
        )[0]
        extreme_summary = {"matching_burst_count": summary["matching_burst_count"], "burst_extreme_value": summary["burst_extreme_value"]}
    pagination_sql = "" if all_results else "LIMIT ? OFFSET ?"
    item_parameters = parameters if all_results else [*parameters, limit, offset]
    items = database.query(
        f"""SELECT r.request_id, r.start_utc, r.actor_id, a.ip AS actor_ip,
                      a.provider, a.country, a.city, a.asn, r.host_id, h.name AS host,
                      (SELECT br.burst_id FROM burst_request AS br WHERE br.request_id = r.request_id LIMIT 1) AS burst_id,
                      CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS host_known,
                      r.request_method, r.request_path, r.request_scheme,
                      (SELECT GROUP_CONCAT(c.category_name, ', ')
                       FROM request_category AS rc
                       JOIN category AS c ON c.category_id = rc.category_id
                       WHERE rc.request_id = r.request_id) AS categories,
                      r.downstream_status, r.downstream_content_size, r.request_content_size,
                      r.duration, r.user_agent
               {joins}
               WHERE {where_clause}
               ORDER BY {order_by}
               {pagination_sql}""",
        item_parameters,
    )
    return {
        "items": items,
        "total": total_rows[0]["total"],
        "limit": total_rows[0]["total"] if all_results else limit,
        "offset": 0 if all_results else offset,
        "from": start,
        "to": end,
        **extreme_summary,
    }


@router.get("/request_groups")
def get_request_groups(
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    incident_id: int | None = Query(default=None, ge=1),
    burst_id: int | None = Query(default=None, ge=1),
    burst_extreme: Literal["min_requests", "max_requests", "min_duration", "max_duration"] | None = Query(default=None),
    provider: str | None = Query(default=None, min_length=1),
    provider_exact: bool = Query(default=False),
    country: str | None = Query(default=None, min_length=1),
    country_exact: bool = Query(default=False),
    actor: str | None = Query(default=None, min_length=1),
    actor_exact: bool = Query(default=False),
    host: str | None = Query(default=None, min_length=1),
    host_exact: bool = Query(default=False),
    category: str | None = Query(default=None, min_length=1),
    category_exact: bool = Query(default=False),
    path: str | None = Query(default=None, min_length=1),
    path_exact: bool = Query(default=False),
    search: str | None = Query(default=None, min_length=1),
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = Query(default=None),
    without_burst: bool = Query(default=False),
    sort_by: Literal["first_time", "host", "actor_ip", "request_count"] = Query(default="first_time"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=30, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return requests grouped by the exact host and actor combination."""
    start, end = _utc_timestamp(from_), _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    conditions = ["r.start_utc >= ?", "r.start_utc < ?"]
    parameters: list[Any] = [start, end]
    if incident_id is not None:
        conditions.append(incident_request_condition())
        parameters.extend(incident_request_parameters(incident_id))
    if burst_id is not None:
        conditions.append("EXISTS (SELECT 1 FROM burst_request AS br WHERE br.burst_id = ? AND br.request_id = r.request_id)")
        parameters.append(burst_id)
    if burst_extreme is not None:
        if burst_extreme.endswith("requests"):
            outer_value, inner_value = "be.read_count + be.write_count + be.other_count", "read_count + write_count + other_count"
        else:
            outer_value, inner_value = "(julianday(be.end_time) - julianday(be.start_time))", "(julianday(end_time) - julianday(start_time))"
        aggregate = "MIN" if burst_extreme.startswith("min_") else "MAX"
        conditions.append(f"""EXISTS (SELECT 1 FROM burst_request AS bre JOIN burst AS be ON be.burst_id = bre.burst_id
            WHERE bre.request_id = r.request_id AND be.start_time >= ? AND be.start_time < ?
            AND {outer_value} = (SELECT {aggregate}({inner_value}) FROM burst WHERE start_time >= ? AND start_time < ?))""")
        parameters.extend([start, end, start, end])
    if without_burst:
        conditions.append("NOT EXISTS (SELECT 1 FROM burst_request AS br WHERE br.request_id = r.request_id)")
    for column, value, exact in (("a.provider", provider, provider_exact), ("a.country", country, country_exact), ("a.ip", actor, actor_exact), ("h.name", host, host_exact)):
        if value is not None:
            conditions.append(f"TRIM({column}) = ?" if exact and column in {"a.provider", "a.country"} else f"{column} = ?" if exact else f"{column} LIKE ?")
            parameters.append(value if exact else f"%{value}%")
    for column, value, exact in (("category", category, category_exact), ("path", path, path_exact)):
        if value is not None:
            if column == "category":
                conditions.append("EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name " + ("= ?" if exact else "LIKE ?") + ")")
            else:
                conditions.append(f"r.request_path {'=' if exact else 'LIKE'} ?")
            parameters.append(value if exact else f"%{value}%")
    if search is not None:
        field, term = parse_search(search)
        if not term:
            conditions.append("0")
        elif field is None:
            conditions.append("(a.ip LIKE ? OR h.name LIKE ? OR a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ? OR r.request_path LIKE ? OR r.request_method LIKE ? OR r.request_scheme LIKE ? OR CAST(r.downstream_status AS TEXT) LIKE ? OR COALESCE(r.user_agent, '') LIKE ? OR r.start_utc LIKE ? OR CAST(r.duration AS TEXT) LIKE ? OR CAST(r.downstream_content_size AS TEXT) LIKE ? OR CAST(r.request_content_size AS TEXT) LIKE ? OR CAST((SELECT br.burst_id FROM burst_request AS br WHERE br.request_id = r.request_id LIMIT 1) AS TEXT) LIKE ? OR EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id = src.category_id WHERE src.request_id = r.request_id AND sc.category_name LIKE ?))")
            parameters.extend([f"%{term}%"] * 17)
        elif field == "actor":
            conditions.append("(a.ip LIKE ? OR COALESCE(a.country,'') LIKE ? OR COALESCE(a.city,'') LIKE ? OR COALESCE(a.provider,'') LIKE ? OR COALESCE(a.asn,'') LIKE ?)")
            parameters.extend([f"%{term}%"] * 5)
        elif field == "location":
            conditions.append("(a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ?)")
            parameters.extend([f"%{term}%"] * 4)
        elif field == "category":
            conditions.append("EXISTS (SELECT 1 FROM request_category AS rc JOIN category AS c ON c.category_id = rc.category_id WHERE rc.request_id = r.request_id AND c.category_name LIKE ?)")
            parameters.append(f"%{term}%")
        elif field in {"ip", "host", "country", "city", "provider", "asn", "path", "method", "scheme", "user_agent", "time", "duration", "status", "response_size", "request_body_size", "burst_id", "incident_id"}:
            columns = {"ip": "a.ip", "host": "h.name", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn", "path": "r.request_path", "method": "r.request_method", "scheme": "r.request_scheme", "user_agent": "r.user_agent", "time": "r.start_utc", "duration": "r.duration", "status": "r.downstream_status", "response_size": "r.downstream_content_size", "request_body_size": "r.request_content_size", "burst_id": "(SELECT br.burst_id FROM burst_request AS br WHERE br.request_id = r.request_id LIMIT 1)"}
            if field == "incident_id":
                conditions.append(incident_request_condition())
                parameters.extend(incident_request_parameters(int(term)) if term.isdigit() else [0])
            else:
                column = columns.get(field)
                if column is None:
                    conditions.append("0")
                else:
                    conditions.append(f"CAST({column} AS TEXT) LIKE ?" if field in {"duration", "status", "response_size", "request_body_size", "burst_id"} else f"{column} LIKE ?")
                    parameters.append(f"%{term}%")
        else:
            conditions.append("0")
    if status_class is not None:
        status_start = int(status_class[0]) * 100
        conditions.append("r.downstream_status >= ? AND r.downstream_status < ?")
        parameters.extend([status_start, status_start + 100])
    where = " AND ".join(conditions)
    joins = "FROM request AS r JOIN actor AS a ON a.actor_id = r.actor_id LEFT JOIN host AS h ON h.host_id = r.host_id"
    database = get_database(request)
    total = database.query(f"SELECT COUNT(*) AS total FROM (SELECT r.actor_id, r.host_id {joins} WHERE {where} GROUP BY r.actor_id, r.host_id)", parameters)[0]["total"]
    sort_columns = {"first_time": "first_time", "host": "h.name", "actor_ip": "a.ip", "request_count": "request_count"}
    order_by = sort_columns[sort_by]
    direction = sort_order.upper()
    items = database.query(
        f"""SELECT r.actor_id, a.ip AS actor_ip, a.provider, a.asn, a.country, a.city,
                   r.host_id, h.name AS host,
                   CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS host_known,
                   MIN(r.start_utc) AS first_time,
                   MAX(r.start_utc) AS last_time, COUNT(*) AS request_count
            {joins} WHERE {where} GROUP BY r.actor_id, r.host_id
            ORDER BY {order_by} {direction}, last_time DESC, a.ip ASC, h.name ASC LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset, "from": start, "to": end}
