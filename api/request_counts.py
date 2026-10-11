"""Time-bucketed request counts for charts."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database


router = APIRouter()


def _utc_datetime(value: datetime) -> datetime:
    """Normalize an API timestamp to an aware UTC datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/request_counts")
def get_request_counts(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    bars: int = Query(ge=1, le=500, description="Number of equal-width time buckets"),
    host: str | None = Query(default=None, min_length=1),
    actor_ip: str | None = Query(default=None, min_length=1, description="Actor IP substring"),
    actor_id: int | None = Query(default=None, ge=1),
    category: str | None = Query(default=None, min_length=1),
) -> dict[str, Any]:
    """Return read, write, and other request counts in equal time buckets."""
    start_dt = _utc_datetime(from_)
    end_dt = _utc_datetime(to)
    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    start = _utc_text(start_dt)
    end = _utc_text(end_dt)
    filter_conditions: list[str] = []
    filter_parameters: list[Any] = []
    if host is not None:
        filter_conditions.append(
            "EXISTS (SELECT 1 FROM host AS fh WHERE fh.host_id = r.host_id AND fh.name LIKE ?)"
        )
        filter_parameters.append(f"%{host}%")
    if actor_ip is not None:
        filter_conditions.append(
            "EXISTS (SELECT 1 FROM actor AS fa WHERE fa.actor_id = r.actor_id AND fa.ip LIKE ?)"
        )
        filter_parameters.append(f"%{actor_ip}%")
    if actor_id is not None:
        filter_conditions.append("r.actor_id = ?")
        filter_parameters.append(actor_id)
    if category is not None:
        filter_conditions.append(
            """EXISTS (
                   SELECT 1 FROM request_category AS rc
                   JOIN category AS c ON c.category_id = rc.category_id
                   WHERE rc.request_id = r.request_id AND c.category_name LIKE ?
               )"""
        )
        filter_parameters.append(f"%{category}%")

    extra_filters = "".join(f" AND ({condition})" for condition in filter_conditions)
    database = get_database(request)
    rows = database.query(
        f"""WITH RECURSIVE
            params(start_jd, end_jd, bucket_count) AS (
                SELECT julianday(?), julianday(?), ?
            ),
            bucket_starts(bucket_index, start_jd) AS (
                SELECT 0, start_jd FROM params
                UNION ALL
                SELECT bucket_index + 1,
                       p.start_jd + (p.end_jd - p.start_jd) * (bucket_index + 1) / p.bucket_count
                FROM bucket_starts CROSS JOIN params AS p
                WHERE bucket_index + 1 < p.bucket_count
            ),
            buckets AS (
                SELECT s.bucket_index, s.start_jd,
                       CASE WHEN s.bucket_index + 1 = p.bucket_count THEN p.end_jd
                            ELSE p.start_jd + (p.end_jd - p.start_jd)
                                 * (s.bucket_index + 1) / p.bucket_count
                       END AS end_jd
                FROM bucket_starts AS s CROSS JOIN params AS p
            )
            SELECT b.bucket_index,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 IN ('GET', 'HEAD', 'OPTIONS') THEN 1 ELSE 0 END) AS read_count,
                   SUM(CASE WHEN UPPER(COALESCE(r.request_method, ''))
                                 IN ('POST', 'PUT', 'PATCH', 'DELETE') THEN 1 ELSE 0 END) AS write_count,
                   SUM(CASE WHEN r.request_id IS NOT NULL
                                 AND UPPER(COALESCE(r.request_method, ''))
                                 NOT IN ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE')
                            THEN 1 ELSE 0 END) AS other_count
            FROM buckets AS b
            LEFT JOIN request AS r
              ON julianday(r.start_utc) >= b.start_jd
             AND julianday(r.start_utc) < b.end_jd
             AND r.start_utc >= ? AND r.start_utc < ?{extra_filters}
            GROUP BY b.bucket_index
            ORDER BY b.bucket_index""",
        [start, end, bars, start, end, *filter_parameters],
    )

    duration = end_dt - start_dt
    total_microseconds = (
        duration.days * 86_400_000_000
        + duration.seconds * 1_000_000
        + duration.microseconds
    )
    items = []
    for row in rows:
        index = row["bucket_index"]
        bucket_start = start_dt + timedelta(microseconds=total_microseconds * index // bars)
        bucket_end = (
            end_dt
            if index + 1 == bars
            else start_dt + timedelta(microseconds=total_microseconds * (index + 1) // bars)
        )
        read_count = row["read_count"] or 0
        write_count = row["write_count"] or 0
        other_count = row["other_count"] or 0
        items.append(
            {
                "from": _utc_text(bucket_start),
                "to": _utc_text(bucket_end),
                "read_count": read_count,
                "write_count": write_count,
                "other_count": other_count,
                "total_count": read_count + write_count + other_count,
            }
        )

    return {"items": items, "from": start, "to": end, "bars": bars}
