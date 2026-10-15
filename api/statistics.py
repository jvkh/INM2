"""Traffic distribution statistics for the selected time range."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.known_hosts import known_host_match_sql


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

    return {"total_requests": total, **burst_summary, "from": start, "to": end, **result}
