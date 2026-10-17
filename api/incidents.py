"""Search and paginate stored incidents of all supported types."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Path, Query, Request

from api.dependencies import get_database
from common.incidents import attach_incident_types


router = APIRouter()
IncidentType = Literal[
    "path_scan", "failed_login", "sensitive_file_access", "exploit_response",
    "write_activity", "http_error_spike", "scanner_activity", "activity_spike",
    "dormant_host_activity", "low_slow_path_scan",
]


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/path_scan_incidents", include_in_schema=False)
@router.get("/incidents")
def get_incidents(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    search: str | None = Query(default=None, min_length=1),
    state: Literal["open", "acknowledged", "resolved"] | None = Query(default=None),
    incident_type: IncidentType | None = Query(default=None),
    sort_by: Literal["incident_id", "incident_type", "first_seen", "last_seen", "actor_ip", "host", "indicator_count", "request_count", "state"] = Query(default="last_seen"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return incidents overlapping the selected time range."""
    start, end = _utc_text(from_), _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["i.last_seen >= ?", "i.first_seen < ?"]
    parameters: list[Any] = [start, end]
    if state:
        conditions.append("i.state = ?")
        parameters.append(state)
    if incident_type:
        conditions.append("EXISTS (SELECT 1 FROM incident_criterion AS ic WHERE ic.incident_id = i.incident_id AND ic.incident_type = ?)")
        parameters.append(incident_type)
    if search:
        term = f"%{search.strip()}%"
        conditions.append("(a.ip LIKE ? OR a.provider LIKE ? OR a.asn LIKE ? OR a.country LIKE ? OR a.city LIKE ? OR h.name LIKE ? OR i.indicators LIKE ? OR i.summary LIKE ? OR EXISTS (SELECT 1 FROM incident_request AS ir JOIN request AS r ON r.request_id = ir.request_id JOIN host AS ih ON ih.host_id = r.host_id WHERE ir.incident_id = i.incident_id AND ih.name LIKE ?) OR EXISTS (SELECT 1 FROM incident_criterion AS ic WHERE ic.incident_id = i.incident_id AND ic.incident_type LIKE ?))")
        parameters.extend((term, term, term, term, term, term, term, term, term, term))

    database = get_database(request)
    joins = """FROM incident AS i
               JOIN actor AS a ON a.actor_id = i.actor_id
               LEFT JOIN host AS h ON h.host_id = i.host_id"""
    where = " AND ".join(conditions)
    sort_expressions = {
        "incident_id": "i.incident_id", "incident_type": "i.incident_type",
        "first_seen": "i.first_seen", "last_seen": "i.last_seen", "actor_ip": "a.ip",
        "host": "h.name", "indicator_count": "i.indicator_count",
        "request_count": "i.request_count", "state": "i.state",
    }
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, i.incident_id DESC"
    total = database.query(f"SELECT COUNT(*) AS total {joins} WHERE {where}", parameters)[0]["total"]
    items = database.query(
        f"""SELECT i.incident_id, i.incident_type, i.first_seen, i.last_seen,
                   i.request_count, i.indicator_count, i.indicators, i.summary, i.state,
                   a.actor_id, a.ip AS actor_ip, a.country, a.city, a.provider, a.asn,
                   h.name AS host
            {joins}
            WHERE {where}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    for item in items:
        try:
            item["indicators"] = json.loads(item["indicators"])
        except (TypeError, ValueError):
            item["indicators"] = []
        try:
            item["summary"] = json.loads(item["summary"])
        except (TypeError, ValueError):
            item["summary"] = {}
    attach_incident_types(database, items)
    return {"items": items, "total": total, "limit": limit, "offset": offset, "from": start, "to": end}


@router.get("/incident_statistics")
def get_incident_statistics(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    include_incidents: bool = Query(default=False, description="Include incident details in each timeline bucket"),
) -> dict[str, Any]:
    """Aggregate incidents by type, time, actor, host, and detector metrics."""
    start, end = _utc_text(from_), _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    database = get_database(request)
    where = "i.first_seen >= ? AND i.first_seen < ?"
    totals = database.query(
        f"""SELECT COUNT(*) AS incident_count, COUNT(DISTINCT i.actor_id) AS actor_count,
                   COALESCE(SUM(i.request_count), 0) AS linked_request_count
            FROM incident AS i WHERE {where}""", (start, end),
    )[0]
    totals["host_count"] = database.query(
        f"""SELECT COUNT(DISTINCT r.host_id) AS host_count FROM incident AS i
            JOIN incident_request AS ir ON ir.incident_id = i.incident_id
            JOIN request AS r ON r.request_id = ir.request_id WHERE {where}""", (start, end),
    )[0]["host_count"]
    by_type = database.query(
        f"""SELECT ic.incident_type AS name, COUNT(DISTINCT i.incident_id) AS request_count
            FROM incident AS i JOIN incident_criterion AS ic ON ic.incident_id = i.incident_id
            WHERE {where}
            GROUP BY ic.incident_type ORDER BY request_count DESC, name""", (start, end),
    )
    total_incidents = totals["incident_count"]
    by_type = [{**row, "share_percent": row["request_count"] * 100 / total_incidents if total_incidents else 0} for row in by_type]
    actors = database.query(
        f"""SELECT a.ip AS name, a.provider, a.asn, a.country, a.city,
                   COUNT(*) AS request_count
            FROM incident AS i JOIN actor AS a ON a.actor_id = i.actor_id WHERE {where}
            GROUP BY a.actor_id ORDER BY request_count DESC, a.ip COLLATE NOCASE LIMIT 10""", (start, end),
    )
    hosts = database.query(
        f"""SELECT h.name AS name, COUNT(DISTINCT i.incident_id) AS request_count
            FROM incident AS i JOIN incident_request AS ir ON ir.incident_id = i.incident_id
            JOIN request AS r ON r.request_id = ir.request_id
            JOIN host AS h ON h.host_id = r.host_id WHERE {where}
            GROUP BY h.host_id ORDER BY request_count DESC, h.name COLLATE NOCASE LIMIT 10""", (start, end),
    )
    for rows in (actors, hosts):
        for row in rows:
            row["share_percent"] = row["request_count"] * 100 / total_incidents if total_incidents else 0

    start_dt = from_.replace(tzinfo=timezone.utc) if from_.tzinfo is None else from_.astimezone(timezone.utc)
    end_dt = to.replace(tzinfo=timezone.utc) if to.tzinfo is None else to.astimezone(timezone.utc)
    span_us = int((end_dt - start_dt).total_seconds() * 1_000_000)
    bucket_ranges = [
        (start_dt + timedelta(microseconds=span_us * index // 24),
         end_dt if index == 23 else start_dt + timedelta(microseconds=span_us * (index + 1) // 24))
        for index in range(24)
    ]
    values_sql = ", ".join("(?, ?, ?)" for _ in bucket_ranges)
    bucket_params = [value for index, (bucket_start, bucket_end) in enumerate(bucket_ranges)
                     for value in (index, _utc_text(bucket_start), _utc_text(bucket_end))]
    timeline = database.query(
        f"""WITH buckets(bucket_index, bucket_from, bucket_to) AS (VALUES {values_sql})
            SELECT b.bucket_index, b.bucket_from AS "from", b.bucket_to AS "to",
                   COUNT(i.incident_id) AS incident_count
            FROM buckets AS b LEFT JOIN incident AS i
              ON i.first_seen >= b.bucket_from AND i.first_seen < b.bucket_to
            GROUP BY b.bucket_index ORDER BY b.bucket_index""", bucket_params,
    )
    if include_incidents:
        incident_rows = database.query(
            f"""WITH buckets(bucket_index, bucket_from, bucket_to) AS (VALUES {values_sql})
                SELECT b.bucket_index, i.incident_id, i.incident_type, i.first_seen, i.last_seen,
                       i.request_count, i.indicator_count, i.indicators, i.summary,
                       a.ip AS actor_ip, a.country, a.city, a.provider, a.asn, h.name AS host
                FROM buckets AS b JOIN incident AS i
                  ON i.first_seen >= b.bucket_from AND i.first_seen < b.bucket_to
                JOIN actor AS a ON a.actor_id = i.actor_id
                LEFT JOIN host AS h ON h.host_id = i.host_id
                ORDER BY b.bucket_index, i.first_seen, i.incident_id""", bucket_params,
        )
        for bucket in timeline:
            bucket["incidents"] = []
        for item in incident_rows:
            for field in ("indicators", "summary"):
                try:
                    item[field] = json.loads(item[field] or ("[]" if field == "indicators" else "{}"))
                except (TypeError, ValueError):
                    item[field] = [] if field == "indicators" else {}
        attach_incident_types(database, incident_rows)
        for item in incident_rows:
            timeline[item["bucket_index"]]["incidents"].append({
                key: value for key, value in item.items() if key != "bucket_index"
            })

    summaries = database.query(
        f"""SELECT ic.incident_type, i.summary FROM incident AS i
            JOIN incident_criterion AS ic ON ic.incident_id = i.incident_id
            WHERE {where} AND ic.incident_type IN ('http_error_spike', 'activity_spike')""", (start, end),
    )
    error_incident_count = activity_incident_count = 0
    error_count = non_error_count = 0
    average_rates: list[float] = []
    min_rates: list[float] = []
    max_rates: list[float] = []
    for row in summaries:
        try:
            summary = json.loads(row["summary"] or "{}")
        except (TypeError, ValueError):
            summary = {}
        if row["incident_type"] == "http_error_spike":
            error_incident_count += 1
            error_count += int(summary.get("error_count", 0))
            non_error_count += int(summary.get("non_error_count", 0))
        else:
            activity_incident_count += 1
            if isinstance(summary.get("average_rps"), (int, float)):
                average_rates.append(float(summary["average_rps"]))
            if isinstance(summary.get("min_rps"), (int, float)):
                min_rates.append(float(summary["min_rps"]))
            if isinstance(summary.get("max_rps"), (int, float)):
                max_rates.append(float(summary["max_rps"]))
    response_count = error_count + non_error_count
    return {
        **totals,
        "by_type": by_type,
        "timeline": timeline,
        "top_actors": actors,
        "top_hosts": hosts,
        "error_metrics": {
            "incident_count": error_incident_count,
            "error_count": error_count,
            "non_error_count": non_error_count,
            "non_error_share_percent": non_error_count * 100 / response_count if response_count else 0,
        },
        "request_spike_metrics": {
            "incident_count": activity_incident_count,
            "average_rps": sum(average_rates) / len(average_rates) if average_rates else None,
            "min_rps": min(min_rates) if min_rates else None,
            "max_rps": max(max_rates) if max_rates else None,
        },
        "from": start,
        "to": end,
    }


@router.put("/path_scan_incidents/{incident_id}/state", include_in_schema=False)
@router.put("/incidents/{incident_id}/state")
def update_incident_state(
    request: Request,
    incident_id: int = Path(ge=1),
    state: Literal["open", "acknowledged", "resolved"] = Body(embed=True),
) -> dict[str, Any]:
    """Persist an incident workflow state."""
    database = get_database(request)
    cursor = database.execute("UPDATE incident SET state = ? WHERE incident_id = ?", (state, incident_id))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident_id": incident_id, "state": state}
