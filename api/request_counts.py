"""Time-bucketed request counts for charts."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.search import parse_search


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
    host_exact: bool = Query(default=False, description="Match the host exactly"),
    actor_ip: str | None = Query(default=None, min_length=1, description="Actor IP substring"),
    actor_ip_exact: bool = Query(default=False, description="Match the actor IP exactly"),
    actor_id: int | None = Query(default=None, ge=1),
    category: str | None = Query(default=None, min_length=1),
    category_exact: bool = Query(default=False, description="Match the category name exactly"),
    path: str | None = Query(default=None, min_length=1, description="Request-path substring"),
    path_exact: bool = Query(default=False, description="Match the request path exactly"),
    burst_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, description="Search across request fields; qualify with field:value such as host:example.org or pfad:/login"),
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
            "EXISTS (SELECT 1 FROM host AS fh WHERE fh.host_id = r.host_id AND fh.name = ?)" if host_exact else
            "EXISTS (SELECT 1 FROM host AS fh WHERE fh.host_id = r.host_id AND fh.name LIKE ?)"
        )
        filter_parameters.append(host if host_exact else f"%{host}%")
    if actor_ip is not None:
        filter_conditions.append(
            "EXISTS (SELECT 1 FROM actor AS fa WHERE fa.actor_id = r.actor_id AND fa.ip = ?)" if actor_ip_exact else
            "EXISTS (SELECT 1 FROM actor AS fa WHERE fa.actor_id = r.actor_id AND fa.ip LIKE ?)"
        )
        filter_parameters.append(actor_ip if actor_ip_exact else f"%{actor_ip}%")
    if actor_id is not None:
        filter_conditions.append("r.actor_id = ?")
        filter_parameters.append(actor_id)
    if category is not None:
        filter_conditions.append(
            """EXISTS (
                   SELECT 1 FROM request_category AS rc
                   JOIN category AS c ON c.category_id = rc.category_id
                   WHERE rc.request_id = r.request_id AND c.category_name = ?
               )"""
            if category_exact else
            """EXISTS (
                   SELECT 1 FROM request_category AS rc
                   JOIN category AS c ON c.category_id = rc.category_id
                   WHERE rc.request_id = r.request_id AND c.category_name LIKE ?
               )"""
        )
        filter_parameters.append(category if category_exact else f"%{category}%")
    if path is not None:
        filter_conditions.append("r.request_path = ?" if path_exact else "r.request_path LIKE ?")
        filter_parameters.append(path if path_exact else f"%{path}%")
    if burst_id is not None:
        filter_conditions.append(
            "EXISTS (SELECT 1 FROM burst_request AS br WHERE br.burst_id = ? AND br.request_id = r.request_id)"
        )
        filter_parameters.append(burst_id)
    if search is not None:
        field, term = parse_search(search)
        if not term:
            filter_conditions.append("0")
        elif field is None:
            filter_conditions.append(
                "EXISTS (SELECT 1 FROM actor AS sa WHERE sa.actor_id = r.actor_id AND (sa.ip LIKE ? OR sa.country LIKE ? OR sa.city LIKE ? OR sa.provider LIKE ? OR sa.asn LIKE ?)) OR r.request_path LIKE ? OR EXISTS (SELECT 1 FROM host AS sh WHERE sh.host_id = r.host_id AND sh.name LIKE ?)"
            )
            filter_parameters.extend([f"%{term}%"] * 7)
        elif field == "category":
            filter_conditions.append("EXISTS (SELECT 1 FROM request_category AS src JOIN category AS sc ON sc.category_id = src.category_id WHERE src.request_id = r.request_id AND sc.category_name LIKE ?)")
            filter_parameters.append(f"%{term}%")
        elif field == "status":
            filter_conditions.append("CAST(r.downstream_status AS TEXT) LIKE ?")
            filter_parameters.append(f"%{term}%")
        elif field in {"ip", "host", "country", "city", "provider", "asn", "path", "method", "scheme", "user_agent"}:
            if field in {"ip", "country", "city", "provider", "asn"}:
                actor_column = {"ip": "ip", "country": "country", "city": "city", "provider": "provider", "asn": "asn"}[field]
                filter_conditions.append(f"EXISTS (SELECT 1 FROM actor AS sa WHERE sa.actor_id = r.actor_id AND sa.{actor_column} LIKE ?)")
                filter_parameters.append(f"%{term}%")
            elif field == "host":
                filter_conditions.append("EXISTS (SELECT 1 FROM host AS sh WHERE sh.host_id = r.host_id AND sh.name LIKE ?)")
                filter_parameters.append(f"%{term}%")
            else:
                column = {"path": "request_path", "method": "request_method", "scheme": "request_scheme", "user_agent": "user_agent"}.get(field)
                if column is None:
                    filter_conditions.append("0")
                else:
                    filter_conditions.append(f"{column} LIKE ?")
                    filter_parameters.append(f"%{term}%")
        else:
            filter_conditions.append("0")
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
        for index in range(bucket_count):
            bucket_start = start_dt + timedelta(microseconds=total_microseconds * index // bucket_count)
            bucket_end = end_dt if index + 1 == bucket_count else start_dt + timedelta(microseconds=total_microseconds * (index + 1) // bucket_count)
            fixed_buckets.append((bucket_start, bucket_end))

    database = get_database(request)
    bucket_values = ", ".join("(?, ?, ?)" for _ in fixed_buckets)
    bucket_cte = f"buckets(bucket_index, start_utc, end_utc) AS (VALUES {bucket_values})"
    bucket_parameters = [
        value
        for index, (bucket_start, bucket_end) in enumerate(fixed_buckets)
        for value in (index, _utc_text(bucket_start), _utc_text(bucket_end))
    ]
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
              ON r.start_utc >= b.start_utc
             AND r.start_utc < b.end_utc{extra_filters}
            GROUP BY b.bucket_index
            ORDER BY b.bucket_index""",
        [*bucket_parameters, *filter_parameters],
    )

    items = []
    for row in rows:
        index = row["bucket_index"]
        bucket_start, bucket_end = fixed_buckets[index]
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
