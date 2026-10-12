"""Time-bucketed request counts for charts."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    bucket_minutes: int | None = Query(default=None, ge=1, le=4320, description="Fixed bucket width in minutes"),
    bucket_anchor: datetime | None = Query(default=None, description="Local interval boundary used to align fixed buckets"),
    bucket_timezone: str | None = Query(default=None, description="IANA timezone for calendar-aligned buckets"),
    host: str | None = Query(default=None, min_length=1),
    actor_ip: str | None = Query(default=None, min_length=1, description="Actor IP substring"),
    actor_id: int | None = Query(default=None, ge=1),
    category: str | None = Query(default=None, min_length=1),
    burst_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, description="Search IP, country, city, provider, ASN, or request path"),
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = Query(default=None),
) -> dict[str, Any]:
    """Return request counts in equal-width or fixed-duration time buckets."""
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
    if burst_id is not None:
        filter_conditions.append(
            """EXISTS (
                   SELECT 1 FROM burst AS fb
                   WHERE fb.burst_id = ?
                     AND fb.actor_id = r.actor_id
                     AND fb.host_id IS r.host_id
                     AND r.start_utc >= fb.start_time
                     AND r.start_utc <= fb.end_time
               )"""
        )
        filter_parameters.append(burst_id)
    if search is not None:
        filter_conditions.append(
            "EXISTS (SELECT 1 FROM actor AS sa WHERE sa.actor_id = r.actor_id AND (sa.ip LIKE ? OR sa.country LIKE ? OR sa.city LIKE ? OR sa.provider LIKE ? OR sa.asn LIKE ?)) OR r.request_path LIKE ?"
        )
        filter_parameters.extend([f"%{search}%"] * 6)
    if status_class is not None:
        status_start = int(status_class[0]) * 100
        filter_conditions.append("r.downstream_status >= ? AND r.downstream_status < ?")
        filter_parameters.extend([status_start, status_start + 100])

    extra_filters = "".join(f" AND ({condition})" for condition in filter_conditions)
    duration = end_dt - start_dt
    total_microseconds = (
        duration.days * 86_400_000_000
        + duration.seconds * 1_000_000
        + duration.microseconds
    )
    bucket_microseconds = bucket_minutes * 60_000_000 if bucket_minutes is not None else None
    anchor_dt = _utc_datetime(bucket_anchor) if bucket_anchor is not None else start_dt
    if anchor_dt > start_dt:
        raise HTTPException(status_code=422, detail="'bucket_anchor' must not be later than 'from'")
    fixed_buckets: list[tuple[datetime, datetime]] = []
    if bucket_microseconds:
        try:
            bucket_zone = ZoneInfo(bucket_timezone) if bucket_timezone else timezone.utc
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="'bucket_timezone' must be a valid IANA timezone") from exc
        bucket_start_dt = anchor_dt
        while bucket_start_dt < end_dt:
            local_start = bucket_start_dt.astimezone(bucket_zone)
            if bucket_minutes <= 60:
                next_bucket = bucket_start_dt + timedelta(minutes=bucket_minutes)
            elif bucket_minutes == 480:
                if local_start.hour < 8:
                    next_hour = 8
                    next_date = local_start.date()
                elif local_start.hour < 16:
                    next_hour = 16
                    next_date = local_start.date()
                else:
                    next_hour = 0
                    next_date = local_start.date() + timedelta(days=1)
                next_local = datetime.combine(next_date, datetime.min.time()).replace(
                    hour=next_hour, tzinfo=bucket_zone
                )
                next_bucket = next_local.astimezone(timezone.utc)
            else:
                day_count = bucket_minutes // 1440
                next_date = local_start.date() + timedelta(days=day_count)
                next_local = datetime.combine(next_date, datetime.min.time(), tzinfo=bucket_zone)
                next_bucket = next_local.astimezone(timezone.utc)
            if next_bucket <= bucket_start_dt:
                raise HTTPException(status_code=422, detail="Bucket interval did not advance")
            fixed_buckets.append((bucket_start_dt, min(next_bucket, end_dt)))
            bucket_start_dt = next_bucket
        bucket_count = len(fixed_buckets)
    else:
        bucket_count = bars
        bucket_days = duration.total_seconds() / 86_400 / bars
    database = get_database(request)
    if bucket_microseconds:
        bucket_values = ", ".join("(?, julianday(?), julianday(?))" for _ in fixed_buckets)
        bucket_cte = f"buckets(bucket_index, start_jd, end_jd) AS (VALUES {bucket_values})"
        bucket_parameters = [
            value
            for index, (bucket_start, bucket_end) in enumerate(fixed_buckets)
            for value in (index, _utc_text(bucket_start), _utc_text(bucket_end))
        ]
    else:
        bucket_cte = """RECURSIVE
            params(start_jd, end_jd, bucket_count, bucket_days) AS (
                SELECT julianday(?), julianday(?), ?, ?
            ),
            bucket_starts(bucket_index, start_jd) AS (
                SELECT 0, start_jd FROM params
                UNION ALL
                SELECT bucket_index + 1,
                       p.start_jd + p.bucket_days * (bucket_index + 1)
                FROM bucket_starts CROSS JOIN params AS p
                WHERE bucket_index + 1 < p.bucket_count
            ),
            buckets AS (
                SELECT s.bucket_index, s.start_jd,
                       MIN(p.start_jd + p.bucket_days * (s.bucket_index + 1), p.end_jd) AS end_jd
                FROM bucket_starts AS s CROSS JOIN params AS p
            )"""
        bucket_parameters = [_utc_text(start_dt), end, bucket_count, bucket_days]
    rows = database.query(
        f"""WITH {bucket_cte}
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
        [*bucket_parameters, start, end, *filter_parameters],
    )

    items = []
    for row in rows:
        index = row["bucket_index"]
        if bucket_microseconds is not None:
            bucket_start, bucket_end = fixed_buckets[index]
        else:
            bucket_start = start_dt + timedelta(microseconds=total_microseconds * index // bars)
            bucket_end = end_dt if index + 1 == bars else start_dt + timedelta(microseconds=total_microseconds * (index + 1) // bars)
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

    return {"items": items, "from": start, "to": end, "bars": bucket_count}
