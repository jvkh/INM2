"""Honeypot event browsing endpoints."""

import base64
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from api.status import _honeypot_is_configured

router = APIRouter()
BODY_DIRECTORY = Path(os.environ.get("HONEYPOT_BODY_DIR", "/logs/honeypot-bodies"))


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/honeypot/summary")
def get_honeypot_summary(
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
) -> dict[str, int]:
    """Return period-only counters for the Honeypot request page."""
    if not _honeypot_is_configured():
        raise HTTPException(status_code=404, detail="Honeypot is not configured")
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    row = get_database(request).query(
        """SELECT COUNT(*) AS request_count,
                  COUNT(DISTINCT NULLIF(client_ip, '')) AS actor_count,
                  SUM(CASE WHEN UPPER(method) = 'POST' AND body_bytes > 0 THEN 1 ELSE 0 END) AS post_with_data_count,
                  SUM(CASE WHEN session_phase = 'uploaded-execution-attempt'
                                OR rule = 'uploaded-execution-attempt' THEN 1 ELSE 0 END) AS uploaded_execution_attempt_count
           FROM honeypot_event WHERE time >= ? AND time < ?""",
        (start, end),
    )[0]
    return {key: int(row[key] or 0) for key in (
        "request_count", "actor_count", "post_with_data_count", "uploaded_execution_attempt_count"
    )}


@router.get("/honeypot/statistics")
def get_honeypot_statistics(
    request: Request,
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
) -> dict[str, Any]:
    """Summarize captured honeypot events and approximate incident matches."""
    if not _honeypot_is_configured():
        raise HTTPException(status_code=404, detail="Honeypot is not configured")
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    database = get_database(request)
    total = database.query(
        "SELECT COUNT(*) AS count FROM honeypot_event WHERE time >= ? AND time < ?", (start, end)
    )[0]["count"]

    def distributions(column: str) -> list[dict[str, Any]]:
        rows = database.query(
            f"""SELECT COALESCE(NULLIF({column}, ''), 'Unbekannt') AS name, COUNT(*) AS request_count
                FROM honeypot_event WHERE time >= ? AND time < ?
                GROUP BY COALESCE(NULLIF({column}, ''), 'Unbekannt')
                ORDER BY request_count DESC, name LIMIT 20""",
            (start, end),
        )
        return [
            {**row, "share_percent": round(row["request_count"] * 100 / total, 2) if total else 0}
            for row in rows
        ]

    # Events and proxy requests are separate records. This bounded match is an
    # estimate, requiring the same actor, host, method, path and a 10s window.
    matches = database.query(
        """SELECT COUNT(DISTINCT e.event_id) AS matched_access_count,
                  COUNT(DISTINCT ir.incident_id) AS matched_incident_count
           FROM honeypot_event e
           JOIN actor a ON a.ip = e.client_ip
           JOIN host h ON lower(h.name) = lower(e.host)
           JOIN request r ON r.actor_id = a.actor_id AND r.host_id = h.host_id
           JOIN incident_request ir ON ir.request_id = r.request_id
           WHERE e.time >= ? AND e.time < ? AND r.request_method = e.method
             AND substr(r.request_path, 1, instr(r.request_path || '?', '?') - 1) = e.path
             AND abs((julianday(r.start_utc) - julianday(e.time)) * 86400) <= 10""",
        (start, end),
    )[0]
    bucket_count = 24
    start_dt = from_
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    end_dt = to
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    duration = (end_dt - start_dt) / bucket_count
    buckets = []
    for index in range(bucket_count):
        bucket_start = start_dt + duration * index
        bucket_end = start_dt + duration * (index + 1)
        buckets.append({"from": _utc_timestamp(bucket_start), "to": _utc_timestamp(bucket_end)})
    timeline_rows = database.query(
        """WITH buckets(bucket_index, start_utc, end_utc) AS (VALUES """
        + ",".join("(?, ?, ?)" for _ in buckets)
        + """) SELECT b.bucket_index, b.start_utc AS \"from\", b.end_utc AS \"to\",
                     COUNT(e.event_id) AS request_count
             FROM buckets b LEFT JOIN honeypot_event e
               ON e.time >= b.start_utc AND e.time < b.end_utc
             GROUP BY b.bucket_index ORDER BY b.bucket_index""",
        [value for index, bucket in enumerate(buckets) for value in (index, bucket["from"], bucket["to"])],
    )
    matched = matches["matched_access_count"]
    return {
        "access_count": total,
        "matched_access_count": matched,
        "unmatched_access_count": max(0, total - matched),
        "matched_incident_count": matches["matched_incident_count"],
        "by_method": distributions("method"),
        "by_rule": distributions("rule"),
        "timeline": timeline_rows,
    }


@router.get("/honeypot/events")
def list_honeypot_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    method: str | None = Query(default=None, min_length=1, max_length=16),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=300),
    sort_by: Literal["time", "client_ip", "method", "path", "rule", "body_bytes", "status", "has_body"] = Query(default="time"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> dict[str, Any]:
    database = get_database(request)
    conditions: list[str] = []
    parameters: list[Any] = []
    if from_ is not None:
        conditions.append("e.time >= ?")
        parameters.append(_utc_timestamp(from_))
    if to is not None:
        conditions.append("e.time < ?")
        parameters.append(_utc_timestamp(to))
    if from_ is not None and to is not None and _utc_timestamp(from_) >= _utc_timestamp(to):
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    if method:
        conditions.append("e.method = ?")
        parameters.append(method.upper())
    if search:
        term = f"%{search.strip()}%"
        searchable = (
            "e.event_id", "e.time", "e.client_ip", "COALESCE(e.provider, a.provider)",
            "COALESCE(e.asn, a.asn)", "COALESCE(e.country, a.country)", "COALESCE(e.city, a.city)",
            "e.host", "e.session_id", "e.session_phase", "e.method", "e.path", "e.user_agent", "e.content_type", "e.body_bytes",
            "e.body_clipped", "e.body_sha256", "e.rule", "e.status", "e.body_text", "e.body_base64", "e.body_file",
        )
        conditions.append("(" + " OR ".join(f"COALESCE(CAST({column} AS TEXT), '') LIKE ?" for column in searchable) + ")")
        parameters.extend([term] * len(searchable))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    total = database.query(
        f"SELECT COUNT(*) AS total FROM honeypot_event AS e LEFT JOIN actor AS a ON a.ip = e.client_ip {where}",
        parameters,
    )[0]["total"]
    sort_columns = {
        "time": "e.time", "client_ip": "e.client_ip", "method": "e.method",
        "path": "e.path", "rule": "e.rule", "body_bytes": "e.body_bytes",
        "status": "e.status", "has_body": "has_body",
    }
    items = database.query(
        f"""SELECT e.event_id, e.time, e.client_ip,
                   COALESCE(e.provider, a.provider) AS provider,
                   COALESCE(e.asn, a.asn) AS asn,
                   COALESCE(e.country, a.country) AS country,
                   COALESCE(e.city, a.city) AS city,
                   e.method, e.path, e.user_agent, e.content_type, e.host, e.scheme, e.session_id, e.session_phase,
                   e.body_bytes, e.body_clipped, e.body_sha256, e.rule, e.status, e.duration,
                   CASE WHEN e.body_text IS NOT NULL OR e.body_base64 IS NOT NULL OR e.body_file IS NOT NULL
                        THEN 1 ELSE 0 END AS has_body
            FROM honeypot_event AS e LEFT JOIN actor AS a ON a.ip = e.client_ip {where}
            ORDER BY {sort_columns[sort_by]} {sort_order.upper()}, e.event_id {sort_order.upper()} LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/honeypot/groups")
def list_honeypot_groups(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    method: str | None = Query(default=None, min_length=1, max_length=16),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=300),
    sort_by: Literal["time", "client_ip", "request_count", "post_count", "path_count", "body_bytes"] = Query(default="time"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    protected_only: bool = Query(default=False, description="Only actors protected from inactivity cleanup"),
) -> dict[str, Any]:
    """Group consecutive requests from one actor into five-minute sessions."""
    database = get_database(request)
    time_conditions: list[str] = []
    time_parameters: list[Any] = []
    if from_ is not None:
        time_conditions.append("e.time >= ?")
        time_parameters.append(_utc_timestamp(from_))
    if to is not None:
        time_conditions.append("e.time < ?")
        time_parameters.append(_utc_timestamp(to))
    if from_ is not None and to is not None and _utc_timestamp(from_) >= _utc_timestamp(to):
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    match_conditions = list(time_conditions)
    match_parameters = list(time_parameters)
    if protected_only:
        match_conditions.append("EXISTS (SELECT 1 FROM maintenance_exclusion AS me WHERE me.ip = e.client_ip)")
    if method:
        match_conditions.append("e.method = ?")
        match_parameters.append(method.upper())
    if search:
        term = f"%{search.strip()}%"
        searchable = (
            "e.event_id", "e.time", "e.client_ip", "COALESCE(e.provider, a.provider)",
            "COALESCE(e.asn, a.asn)", "COALESCE(e.country, a.country)", "COALESCE(e.city, a.city)",
            "e.host", "e.scheme", "e.session_id", "e.session_phase", "e.method", "e.path", "e.user_agent", "e.content_type",
            "e.body_bytes", "e.body_clipped", "e.body_sha256", "e.rule", "e.status",
            "e.body_text", "e.body_base64", "e.body_file",
        )
        match_conditions.append("(" + " OR ".join(f"COALESCE(CAST({column} AS TEXT), '') LIKE ?" for column in searchable) + ")")
        match_parameters.extend([term] * len(searchable))
    where_time = f"WHERE {' AND '.join(time_conditions)}" if time_conditions else ""
    where_match = f"WHERE {' AND '.join(match_conditions)}" if match_conditions else ""
    grouped_ctes = f"""WITH filtered AS (
        SELECT e.event_id, e.time, e.client_ip,
               COALESCE(e.provider, a.provider) AS provider,
               COALESCE(e.asn, a.asn) AS asn,
               COALESCE(e.country, a.country) AS country,
               COALESCE(e.city, a.city) AS city,
               e.method, e.path, e.body_bytes,
               CASE WHEN e.body_text IS NOT NULL OR e.body_base64 IS NOT NULL OR e.body_file IS NOT NULL
                    THEN 1 ELSE 0 END AS has_body
        FROM honeypot_event AS e LEFT JOIN actor AS a ON a.ip = e.client_ip {where_time}
    ), lagged AS (
        SELECT *, LAG(time) OVER (PARTITION BY COALESCE(client_ip, '') ORDER BY time, event_id) AS previous_time
        FROM filtered
    ), marked AS (
        SELECT *, CASE WHEN previous_time IS NULL OR (julianday(time) - julianday(previous_time)) * 86400.0 > 300
                       THEN 1 ELSE 0 END AS new_session
        FROM lagged
    ), numbered AS (
        SELECT *, SUM(new_session) OVER (
            PARTITION BY COALESCE(client_ip, '') ORDER BY time, event_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS session_number
        FROM marked
    ), matching_events AS (
        SELECT e.event_id FROM honeypot_event AS e LEFT JOIN actor AS a ON a.ip = e.client_ip {where_match}
    ), matching_sessions AS (
        SELECT DISTINCT n.client_ip, n.session_number
        FROM numbered AS n JOIN matching_events AS m ON m.event_id = n.event_id
    ), grouped AS (
        SELECT MIN(n.time) AS first_time, MAX(n.time) AS last_time, n.client_ip,
               MAX(n.provider) AS provider, MAX(n.asn) AS asn, MAX(n.country) AS country, MAX(n.city) AS city,
               COUNT(*) AS request_count,
               SUM(CASE WHEN UPPER(n.method) = 'POST' THEN 1 ELSE 0 END) AS post_count,
               SUM(n.has_body) AS body_count, SUM(n.body_bytes) AS body_bytes,
               COUNT(DISTINCT n.path) AS path_count
        FROM numbered AS n JOIN matching_sessions AS s
          ON n.client_ip IS s.client_ip AND n.session_number = s.session_number
        GROUP BY COALESCE(n.client_ip, ''), n.session_number
    )"""
    total = database.query(f"{grouped_ctes} SELECT COUNT(*) AS total FROM grouped", [*time_parameters, *match_parameters])[0]["total"]
    total_events = database.query(f"{grouped_ctes} SELECT COUNT(*) AS total FROM matching_events", [*time_parameters, *match_parameters])[0]["total"]
    sort_columns = {
        "time": "first_time", "client_ip": "client_ip", "request_count": "request_count",
        "post_count": "post_count", "path_count": "path_count", "body_bytes": "body_bytes",
    }
    items = database.query(
        f"""{grouped_ctes}
            SELECT first_time, last_time, client_ip, provider, asn, country, city,
                   request_count, post_count, body_count, body_bytes, path_count
            FROM grouped
            ORDER BY {sort_columns[sort_by]} {sort_order.upper()}, first_time DESC, client_ip
            LIMIT ? OFFSET ?""",
        [*time_parameters, *match_parameters, limit, offset],
    )
    return {"items": items, "total": total, "total_events": total_events, "limit": limit, "offset": offset, "session_gap_seconds": 300}


@router.get("/honeypot/group-events")
def list_honeypot_group_events(
    request: Request,
    client_ip: str | None = Query(default=None, max_length=64),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    method: str | None = Query(default=None, min_length=1, max_length=16),
    search: str | None = Query(default=None, min_length=1, max_length=300),
) -> dict[str, Any]:
    """Return requests in a selected session for its expandable table row."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start > end:
        raise HTTPException(status_code=422, detail="'from' must not be later than 'to'")
    database = get_database(request)
    conditions = ["e.client_ip IS ?", "e.time >= ?", "e.time <= ?"]
    parameters: list[Any] = [client_ip, start, end]
    if method:
        conditions.append("e.method = ?")
        parameters.append(method.upper())
    if search:
        searchable = (
            "e.event_id", "e.time", "e.client_ip", "COALESCE(e.provider, a.provider)",
            "COALESCE(e.asn, a.asn)", "COALESCE(e.country, a.country)", "COALESCE(e.city, a.city)",
            "e.host", "e.scheme", "e.session_id", "e.session_phase", "e.method", "e.path", "e.user_agent", "e.content_type",
            "e.body_bytes", "e.body_clipped", "e.body_sha256", "e.rule", "e.status",
            "e.body_text", "e.body_base64", "e.body_file",
        )
        conditions.append("(" + " OR ".join(f"COALESCE(CAST({column} AS TEXT), '') LIKE ?" for column in searchable) + ")")
        parameters.extend([f"%{search.strip()}%"] * len(searchable))
    items = database.query(
        f"""SELECT e.event_id, e.time, e.client_ip,
                  COALESCE(e.provider, a.provider) AS provider,
                  COALESCE(e.asn, a.asn) AS asn,
                  COALESCE(e.country, a.country) AS country,
                  COALESCE(e.city, a.city) AS city,
                  e.method, e.path, e.user_agent, e.content_type, e.host, e.scheme, e.session_id, e.session_phase,
                  e.body_bytes, e.body_clipped, e.body_sha256, e.rule, e.status, e.duration,
                  CASE WHEN e.body_text IS NOT NULL OR e.body_base64 IS NOT NULL OR e.body_file IS NOT NULL
                       THEN 1 ELSE 0 END AS has_body
           FROM honeypot_event AS e LEFT JOIN actor AS a ON a.ip = e.client_ip
           WHERE {' AND '.join(conditions)}
           ORDER BY e.time, e.event_id""",
        parameters,
    )
    return {"items": items, "total": len(items)}


@router.delete("/honeypot/groups")
def delete_honeypot_group(
    request: Request,
    client_ip: str = Query(..., max_length=64),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
) -> dict[str, int]:
    """Remove one displayed session, including its stored request bodies."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start > end:
        raise HTTPException(status_code=422, detail="'from' must not be later than 'to'")
    database = get_database(request)
    ip_condition = "client_ip IS NULL" if client_ip == "" else "client_ip = ?"
    parameters: tuple[Any, ...] = (start, end) if client_ip == "" else (client_ip, start, end)
    with database.transaction() as connection:
        rows = connection.execute(
            f"SELECT event_id, body_file FROM honeypot_event WHERE {ip_condition} AND time >= ? AND time <= ?",
            parameters,
        ).fetchall()
        connection.execute(
            f"DELETE FROM honeypot_event WHERE {ip_condition} AND time >= ? AND time <= ?",
            parameters,
        )
    for row in rows:
        event_id, body_file = row["event_id"], row["body_file"]
        if body_file == f"{event_id}.bin":
            try:
                (BODY_DIRECTORY / body_file).unlink(missing_ok=True)
            except OSError:
                pass
    return {"deleted_count": len(rows)}


@router.get("/honeypot/events/{event_id}")
def get_honeypot_event(request: Request, event_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{32}", event_id):
        raise HTTPException(status_code=404, detail="Honeypot event not found")
    database = get_database(request)
    rows = database.query(
        """SELECT e.*,
                  COALESCE(e.provider, a.provider) AS actor_provider,
                  COALESCE(e.asn, a.asn) AS actor_asn,
                  COALESCE(e.country, a.country) AS actor_country,
                  COALESCE(e.city, a.city) AS actor_city
           FROM honeypot_event AS e LEFT JOIN actor AS a ON a.ip = e.client_ip
           WHERE e.event_id = ?""",
        (event_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Honeypot event not found")
    event = rows[0]
    event["provider"] = event.pop("actor_provider")
    event["asn"] = event.pop("actor_asn")
    event["country"] = event.pop("actor_country")
    event["city"] = event.pop("actor_city")
    body = event.pop("body_text", None)
    body_base64 = event.pop("body_base64", None)
    body_file = event.pop("body_file", None)
    if body_file:
        if body_file != f"{event_id}.bin":
            raise HTTPException(status_code=500, detail="Invalid honeypot body reference")
        try:
            raw = (BODY_DIRECTORY / body_file).read_bytes()
        except OSError as exc:
            raise HTTPException(status_code=404, detail="Captured request body file not found") from exc
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            body_base64 = base64.b64encode(raw).decode("ascii")
    event["body_text"] = body
    event["body_base64"] = body_base64
    event["body_file"] = body_file
    return event
