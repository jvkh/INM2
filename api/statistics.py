"""Traffic distribution statistics for the selected time range."""

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.known_hosts import known_host_match_sql
from common.incidents import attach_incident_types


router = APIRouter()


def _utc_text(value: datetime) -> str:
    """Normalize timestamps to the UTC format stored by the collector."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/statistics")
def get_statistics(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
) -> dict[str, Any]:
    """Return complete traffic distributions and burst averages."""
    start = _utc_text(from_)
    end = _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    database = get_database(request)
    total = database.query(
        "SELECT COUNT(*) AS request_count FROM request WHERE start_utc >= ? AND start_utc < ?",
        (start, end),
    )[0]["request_count"]

    distributions = {
        "providers": ("a.provider", "LEFT JOIN actor AS a ON a.actor_id = r.actor_id", "a.provider"),
        "countries": ("a.country", "LEFT JOIN actor AS a ON a.actor_id = r.actor_id", "a.country"),
        "hosts": ("h.name", "LEFT JOIN host AS h ON h.host_id = r.host_id", "h.name"),
    }
    result: dict[str, Any] = {}
    for key, (column, join, group_by) in distributions.items():
        known_column = f", CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS known" if key == "hosts" else ""
        rows = database.query(
            f"""SELECT NULLIF(TRIM({column}), '') AS name, COUNT(*) AS request_count{known_column}
                FROM request AS r
                {join}
                WHERE r.start_utc >= ? AND r.start_utc < ?
                GROUP BY NULLIF(TRIM({group_by}), '')
                ORDER BY request_count DESC, name COLLATE NOCASE ASC""",
            (start, end),
        )
        result[key] = [
            {**row, "share_percent": row["request_count"] * 100 / total if total else 0}
            for row in rows
        ]

    category_rows = database.query(
        """SELECT NULLIF(TRIM(c.category_name), '') AS name,
                  COUNT(DISTINCT r.request_id) AS request_count
           FROM request AS r
           JOIN request_category AS rc ON rc.request_id = r.request_id
           JOIN category AS c ON c.category_id = rc.category_id
           WHERE r.start_utc >= ? AND r.start_utc < ?
           GROUP BY NULLIF(TRIM(c.category_name), '')
           ORDER BY request_count DESC, name COLLATE NOCASE ASC""",
        (start, end),
    )
    result["categories"] = [
        {**row, "share_percent": row["request_count"] * 100 / total if total else 0}
        for row in category_rows
    ]

    burst_summary = database.query(
        """WITH burst_values AS (
               SELECT burst_id, read_count + write_count + other_count AS request_count,
                      (julianday(end_time) - julianday(start_time)) * 86400.0 AS duration_seconds
               FROM burst WHERE start_time >= ? AND start_time < ?
           )
           SELECT COUNT(*) AS burst_count,
                  AVG(request_count) AS avg_requests_per_burst,
                  MIN(request_count) AS min_requests_per_burst,
                  MAX(request_count) AS max_requests_per_burst,
                  AVG(duration_seconds) AS avg_burst_duration_seconds,
                  MIN(duration_seconds) AS min_burst_duration_seconds,
                  MAX(duration_seconds) AS max_burst_duration_seconds,
                  (SELECT request_count FROM burst_values ORDER BY duration_seconds, burst_id LIMIT 1) AS min_duration_request_count,
                  (SELECT request_count FROM burst_values ORDER BY duration_seconds DESC, burst_id LIMIT 1) AS max_duration_request_count
           FROM burst_values""",
        (start, end),
    )[0]

    incident_summary = database.query(
        """SELECT COUNT(*) AS incident_count,
                  AVG(request_count) AS avg_requests_per_incident,
                  MIN(request_count) AS min_requests_per_incident,
                  MAX(request_count) AS max_requests_per_incident,
                  AVG((julianday(last_seen) - julianday(first_seen)) * 86400.0) AS avg_incident_duration_seconds,
                  MIN((julianday(last_seen) - julianday(first_seen)) * 86400.0) AS min_incident_duration_seconds,
                  MAX((julianday(last_seen) - julianday(first_seen)) * 86400.0) AS max_incident_duration_seconds
           FROM incident WHERE first_seen >= ? AND first_seen < ?""",
        (start, end),
    )[0]
    incident_extremes: dict[str, Any] = {}
    for key, order_by in (
        ("min_requests_incident", "i.request_count ASC, i.incident_id ASC"),
        ("max_requests_incident", "i.request_count DESC, i.incident_id ASC"),
        ("min_duration_incident", "julianday(i.last_seen) - julianday(i.first_seen) ASC, i.incident_id ASC"),
        ("max_duration_incident", "julianday(i.last_seen) - julianday(i.first_seen) DESC, i.incident_id ASC"),
    ):
        rows = database.query(
            f"""SELECT i.incident_id, i.incident_type, i.first_seen, i.last_seen,
                       i.request_count, i.indicator_count, i.indicators, i.summary,
                       a.actor_id, a.ip AS actor_ip, a.country, a.city, a.provider, a.asn,
                       h.name AS host
                FROM incident AS i
                JOIN actor AS a ON a.actor_id = i.actor_id
                LEFT JOIN host AS h ON h.host_id = i.host_id
                WHERE i.first_seen >= ? AND i.first_seen < ?
                ORDER BY {order_by} LIMIT 1""",
            (start, end),
        )
        incident = rows[0] if rows else None
        if incident is not None:
            for field, fallback in (("indicators", []), ("summary", {})):
                try:
                    incident[field] = json.loads(incident[field] or ("[]" if field == "indicators" else "{}"))
                except (TypeError, ValueError):
                    incident[field] = fallback
            attach_incident_types(database, [incident])
        incident_extremes[key] = incident
    incident_request_count = database.query(
        """SELECT COUNT(DISTINCT ir.request_id) AS request_count
           FROM incident AS i
           JOIN incident_request AS ir ON ir.incident_id = i.incident_id
           JOIN request AS r ON r.request_id = ir.request_id
           WHERE i.first_seen >= ? AND i.first_seen < ?
             AND r.start_utc >= ? AND r.start_utc < ?""",
        (start, end, start, end),
    )[0]["request_count"]
    result.update(incident_summary)
    result.update(incident_extremes)
    result["incident_request_count"] = incident_request_count
    result["non_incident_request_count"] = total - incident_request_count
    result["incident_request_share_percent"] = incident_request_count * 100 / total if total else 0

    status_rows = database.query(
        """SELECT downstream_status AS code, COUNT(*) AS request_count
           FROM request
           WHERE start_utc >= ? AND start_utc < ? AND downstream_status BETWEEN 100 AND 599
           GROUP BY downstream_status
           ORDER BY downstream_status""",
        (start, end),
    )
    result["status_codes"] = [
        {
            "name": str(row["code"]),
            "status_class": f"{row['code'] // 100}xx",
            "request_count": row["request_count"],
            "share_percent": row["request_count"] * 100 / total if total else 0,
        }
        for row in status_rows
    ]

    burst_rows = database.query(
        """WITH burst_values AS (
               SELECT read_count + write_count + other_count AS request_count
               FROM burst WHERE start_time >= ? AND start_time < ?
           ), buckets(name, lower_bound, upper_bound, sort_order) AS (VALUES
               ('1', 1, 1, 1),
               ('2-5', 2, 5, 2),
               ('6-10', 6, 10, 3),
               ('11-25', 11, 25, 4),
               ('26-50', 26, 50, 5),
               ('51-100', 51, 100, 6),
               ('101-200', 101, 200, 7),
               ('201-300', 201, 300, 8),
               ('301-400', 301, 400, 9),
               ('401-500', 401, 500, 10),
               ('501-600', 501, 600, 11),
               ('601-700', 601, 700, 12),
               ('701-800', 701, 800, 13),
               ('801-900', 801, 900, 14),
               ('901-999', 901, 999, 15),
               ('1000+', 1000, NULL, 16)
           )
           SELECT buckets.name, COUNT(burst_values.request_count) AS request_count
           FROM buckets LEFT JOIN burst_values
             ON burst_values.request_count >= buckets.lower_bound
            AND (buckets.upper_bound IS NULL OR burst_values.request_count <= buckets.upper_bound)
           GROUP BY buckets.name, buckets.sort_order
           ORDER BY buckets.sort_order""",
        (start, end),
    )
    result["burst_sizes"] = [
        {**row, "share_percent": row["request_count"] * 100 / burst_summary["burst_count"] if burst_summary["burst_count"] else 0}
        for row in burst_rows
    ]

    method_rows = database.query(
        """SELECT UPPER(COALESCE(request_method, 'OTHER')) AS name, COUNT(*) AS request_count
           FROM request WHERE start_utc >= ? AND start_utc < ?
           GROUP BY UPPER(COALESCE(request_method, 'OTHER'))
           ORDER BY request_count DESC, name COLLATE NOCASE""",
        (start, end),
    )
    result["methods"] = [
        {**row, "share_percent": row["request_count"] * 100 / total if total else 0}
        for row in method_rows
    ]

    path_rows = database.query(
        """SELECT request_path AS name, COUNT(*) AS request_count
           FROM request WHERE start_utc >= ? AND start_utc < ?
           GROUP BY request_path
           ORDER BY request_count DESC, name COLLATE NOCASE
           LIMIT 20""",
        (start, end),
    )
    result["paths"] = [
        {**row, "share_percent": row["request_count"] * 100 / total if total else 0}
        for row in path_rows
    ]

    start_dt = from_.replace(tzinfo=timezone.utc) if from_.tzinfo is None else from_.astimezone(timezone.utc)
    end_dt = to.replace(tzinfo=timezone.utc) if to.tzinfo is None else to.astimezone(timezone.utc)
    bucket_count = 24
    span_us = int((end_dt - start_dt).total_seconds() * 1_000_000)
    buckets = [
        (start_dt + timedelta(microseconds=span_us * index // bucket_count),
         end_dt if index == bucket_count - 1 else start_dt + timedelta(microseconds=span_us * (index + 1) // bucket_count))
        for index in range(bucket_count)
    ]
    bucket_values = ", ".join("(?, ?, ?)" for _ in buckets)
    bucket_cte = f"buckets(bucket_index, start_utc, end_utc) AS (VALUES {bucket_values})"
    bucket_params = [value for index, (bucket_start, bucket_end) in enumerate(buckets) for value in (index, _utc_text(bucket_start), _utc_text(bucket_end))]
    known_match = known_host_match_sql("h.name")
    host_rows = database.query(
        f"""WITH {bucket_cte}
            SELECT b.bucket_index,
                   SUM(CASE WHEN r.request_id IS NOT NULL AND {known_match} THEN 1 ELSE 0 END) AS known_count,
                   SUM(CASE WHEN r.request_id IS NOT NULL AND h.name IS NOT NULL AND NOT {known_match} THEN 1 ELSE 0 END) AS other_count
            FROM buckets AS b
            LEFT JOIN request AS r ON r.start_utc >= b.start_utc AND r.start_utc < b.end_utc
            LEFT JOIN host AS h ON h.host_id = r.host_id
            GROUP BY b.bucket_index ORDER BY b.bucket_index""",
        bucket_params,
    )
    result["host_traffic"] = [
        {"from": _utc_text(bucket_start), "to": _utc_text(bucket_end), "known_count": row["known_count"] or 0, "other_count": row["other_count"] or 0}
        for row, (bucket_start, bucket_end) in zip(host_rows, buckets)
    ]

    actor_rows = database.query(
        f"""WITH {bucket_cte}, first_hosts AS (
                SELECT r.host_id, MIN(r.start_utc) AS first_seen
                FROM request AS r WHERE r.host_id IS NOT NULL AND r.start_utc < ?
                GROUP BY r.host_id
            )
            SELECT b.bucket_index,
                   (SELECT COUNT(*) FROM actor AS a WHERE a.first_time >= b.start_utc AND a.first_time < b.end_utc) AS actor_count,
                   (SELECT COUNT(*) FROM first_hosts WHERE first_seen >= b.start_utc AND first_seen < b.end_utc) AS host_count
            FROM buckets AS b ORDER BY b.bucket_index""",
        [*bucket_params, end],
    )
    result["new_entities"] = [
        {"from": _utc_text(bucket_start), "to": _utc_text(bucket_end), "actor_count": row["actor_count"] or 0, "host_count": row["host_count"] or 0}
        for row, (bucket_start, bucket_end) in zip(actor_rows, buckets)
    ]

    gap_rows = database.query(
        """WITH ordered AS (
               SELECT start_utc, LAG(start_utc) OVER (ORDER BY start_utc, request_id) AS previous_utc
               FROM request WHERE start_utc >= ? AND start_utc < ?
           ), gaps AS (
               SELECT (julianday(start_utc) - julianday(previous_utc)) * 86400.0 AS seconds
               FROM ordered WHERE previous_utc IS NOT NULL
           )
           SELECT CASE
                    WHEN seconds < 1 THEN '<1 s'
                    WHEN seconds < 5 THEN '1–5 s'
                    WHEN seconds < 30 THEN '5–30 s'
                    WHEN seconds < 300 THEN '30 s–5 min'
                    WHEN seconds < 3600 THEN '5–60 min'
                    ELSE '≥1 h'
                  END AS name, COUNT(*) AS request_count
           FROM gaps GROUP BY name ORDER BY MIN(seconds)""",
        (start, end),
    )
    gap_counts = {row["name"]: row["request_count"] for row in gap_rows}
    gap_labels = ["<1 s", "1–5 s", "5–30 s", "30 s–5 min", "5–60 min", "≥1 h"]
    gap_total = sum(gap_counts.values())
    result["request_gaps"] = [
        {"name": label, "request_count": gap_counts.get(label, 0), "share_percent": gap_counts.get(label, 0) * 100 / gap_total if gap_total else 0}
        for label in gap_labels
    ]

    burst_request_count = database.query(
        """SELECT COUNT(*) AS request_count
           FROM request AS r
           WHERE r.start_utc >= ? AND r.start_utc < ?
             AND EXISTS (SELECT 1 FROM burst_request AS br WHERE br.request_id = r.request_id)""",
        (start, end),
    )[0]["request_count"]
    result["burst_request_count"] = burst_request_count
    result["non_burst_request_count"] = total - burst_request_count
    result["burst_request_share_percent"] = burst_request_count * 100 / total if total else 0

    return {"total_requests": total, **burst_summary, **result, "from": start, "to": end}


@router.get("/statistics/insights")
def get_statistics_insights(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    timezone_name: str = Query(default="UTC", alias="timezone", max_length=64),
) -> dict[str, Any]:
    """Return the larger exploratory distributions only when the corresponding UI tab is opened."""
    start = _utc_text(from_)
    end = _utc_text(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    try:
        display_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="Unknown time zone") from error

    database = get_database(request)
    result: dict[str, Any] = {}
    for key, grouping, joins in (
        ("error_hosts", "h.name", "JOIN host AS h ON h.host_id = r.host_id"),
        ("error_paths", "NULLIF(TRIM(r.request_path), '')", ""),
    ):
        known_column = f", CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS known" if key == "error_hosts" else ""
        rows = database.query(
            f"""SELECT {grouping} AS name{known_column},
                       SUM(CASE WHEN r.downstream_status BETWEEN 400 AND 599 THEN 1 ELSE 0 END) AS request_count,
                       COUNT(*) AS total_count
                FROM request AS r {joins}
                WHERE r.start_utc >= ? AND r.start_utc < ? AND {grouping} IS NOT NULL
                GROUP BY {grouping}
                HAVING SUM(CASE WHEN r.downstream_status BETWEEN 400 AND 599 THEN 1 ELSE 0 END) > 0
                ORDER BY request_count DESC, total_count DESC, name COLLATE NOCASE
                LIMIT 20""",
            (start, end),
        )
        result[key] = [
            {**row, "share_percent": row["request_count"] * 100 / row["total_count"] if row["total_count"] else 0}
            for row in rows
        ]

    actor_rows = database.query(
        """SELECT a.ip AS name, a.provider, a.asn, a.country, a.city,
                  COUNT(*) AS request_count
           FROM request AS r JOIN actor AS a ON a.actor_id = r.actor_id
           WHERE r.start_utc >= ? AND r.start_utc < ?
           GROUP BY a.actor_id
           ORDER BY request_count DESC, a.ip COLLATE NOCASE
           LIMIT 100""",
        (start, end),
    )
    actor_total = database.query(
        "SELECT COUNT(*) AS request_count FROM request WHERE start_utc >= ? AND start_utc < ?",
        (start, end),
    )[0]["request_count"]
    result["active_actors"] = [
        {**row, "share_percent": row["request_count"] * 100 / actor_total if actor_total else 0}
        for row in actor_rows
    ]

    hourly_rows = database.query(
        """SELECT substr(start_utc, 1, 13) AS hour_utc, COUNT(*) AS request_count
           FROM request WHERE start_utc >= ? AND start_utc < ?
           GROUP BY hour_utc""",
        (start, end),
    )
    weekday_hours = [[0 for _ in range(24)] for _ in range(7)]
    for row in hourly_rows:
        utc_hour = datetime.fromisoformat(f"{row['hour_utc']}:00:00+00:00")
        local_hour = utc_hour.astimezone(display_timezone)
        weekday_hours[local_hour.weekday()][local_hour.hour] += row["request_count"]
    result["weekday_hours"] = [
        {"weekday": weekday, "hour": hour, "request_count": weekday_hours[weekday][hour]}
        for weekday in range(7) for hour in range(24)
    ]

    start_dt = from_.replace(tzinfo=timezone.utc) if from_.tzinfo is None else from_.astimezone(timezone.utc)
    end_dt = to.replace(tzinfo=timezone.utc) if to.tzinfo is None else to.astimezone(timezone.utc)
    bucket_count = 24
    span_us = int((end_dt - start_dt).total_seconds() * 1_000_000)
    buckets = [
        (start_dt + timedelta(microseconds=span_us * index // bucket_count),
         end_dt if index == bucket_count - 1 else start_dt + timedelta(microseconds=span_us * (index + 1) // bucket_count))
        for index in range(bucket_count)
    ]
    bucket_values = ", ".join("(?, ?, ?)" for _ in buckets)
    bucket_cte = f"buckets(bucket_index, start_utc, end_utc) AS (VALUES {bucket_values})"
    bucket_params = [value for index, (bucket_start, bucket_end) in enumerate(buckets) for value in (index, _utc_text(bucket_start), _utc_text(bucket_end))]
    trend_rows = database.query(
        f"""WITH {bucket_cte}
            SELECT b.bucket_index, b.start_utc AS from_utc, b.end_utc AS to_utc,
                   SUM(CASE WHEN r.downstream_status BETWEEN 100 AND 199 THEN 1 ELSE 0 END) AS status_1xx,
                   SUM(CASE WHEN r.downstream_status BETWEEN 200 AND 299 THEN 1 ELSE 0 END) AS status_2xx,
                   SUM(CASE WHEN r.downstream_status BETWEEN 300 AND 399 THEN 1 ELSE 0 END) AS status_3xx,
                   SUM(CASE WHEN r.downstream_status BETWEEN 400 AND 499 THEN 1 ELSE 0 END) AS status_4xx,
                   SUM(CASE WHEN r.downstream_status BETWEEN 500 AND 599 THEN 1 ELSE 0 END) AS status_5xx
            FROM buckets AS b LEFT JOIN request AS r
              ON r.start_utc >= b.start_utc AND r.start_utc < b.end_utc
            GROUP BY b.bucket_index ORDER BY b.bucket_index""",
        bucket_params,
    )
    result["status_trend"] = [dict(row) for row in trend_rows]
    return result
