"""Burst listing and summary endpoint."""

from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Path, Query, Request

from api.dependencies import get_database
from common.known_hosts import known_host_match_sql
from common.search import parse_search


router = APIRouter()


def _utc_timestamp(value: datetime) -> str:
    """Normalize timestamps to the UTC format stored by the collector."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@router.get("/burst_requests/{id}")
def get_burst_requests(
    request: Request,
    id: int = Path(ge=1, description="Burst ID"),
) -> dict[str, Any]:
    """Return a burst and its exactly assigned requests."""
    database = get_database(request)
    burst_rows = database.query(
        f"""SELECT b.*, a.ip AS actor_ip, a.country, a.provider, a.asn, a.city,
                  h.name AS host,
                  CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS known
           FROM burst AS b
           JOIN actor AS a ON a.actor_id = b.actor_id
           LEFT JOIN host AS h ON h.host_id = b.host_id
           WHERE b.burst_id = ?""",
        (id,),
    )
    if not burst_rows:
        raise HTTPException(status_code=404, detail="Burst not found")

    burst = burst_rows[0]
    requests = database.query(
        """SELECT r.*
           FROM burst_request AS br
           JOIN request AS r ON r.request_id = br.request_id
           WHERE br.burst_id = ?
           ORDER BY r.start_utc, r.request_id""",
        (id,),
    )
    return {"burst": burst, "requests": requests, "total": len(requests)}


@router.get("/bursts/{id}")
def get_burst_requests(
    request: Request,
    id: int = Path(ge=1, description="Burst ID"),
) -> dict[str, Any]:
    """Return a burst."""
    database = get_database(request)
    burst_rows = database.query(
        f"""SELECT b.*, a.ip AS actor_ip, a.country, a.provider, a.asn, a.city,
                  h.name AS host,
                  CASE WHEN {known_host_match_sql('h.name')} THEN 1 ELSE 0 END AS known
           FROM burst AS b
           JOIN actor AS a ON a.actor_id = b.actor_id
           LEFT JOIN host AS h ON h.host_id = b.host_id
           WHERE b.burst_id = ?""",
        (id,),
    )
    if not burst_rows:
        raise HTTPException(status_code=404, detail="Burst not found")

    return burst_rows[0]

@router.get("/bursts")
def get_bursts(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    actor: str | None = Query(default=None, min_length=1, description="Actor IP substring"),
    actor_id: int | None = Query(default=None, ge=1),
    host: str | None = Query(default=None, min_length=1),
    host_exact: bool = Query(default=False, description="Match the host exactly"),
    known: Literal["own", "foreign"] | None = Query(default=None, description="Limit to known or unknown hosts"),
    country: str | None = Query(default=None, min_length=1),
    country_exact: bool = Query(default=False, description="Match the country exactly"),
    provider: str | None = Query(default=None, min_length=1),
    asn: str | None = Query(default=None, min_length=1),
    city: str | None = Query(default=None, min_length=1),
    search: str | None = Query(default=None, min_length=1, description="Search burst fields; qualify with field:value such as host: or ip:"),
    sort_by: Literal["burst_id", "start_time", "actor_ip", "host", "country", "duration", "requests", "avg_count"] = Query(default="start_time"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return a burst summary and matching bursts for a time range."""
    start = _utc_timestamp(from_)
    end = _utc_timestamp(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    conditions = ["b.start_time >= ?", "b.start_time < ?"]
    parameters: list[Any] = [start, end]
    if host is not None:
        conditions.append("h.name = ?" if host_exact else "h.name LIKE ?")
        parameters.append(host if host_exact else f"%{host}%")
    known_match = known_host_match_sql("h.name")
    if known == "own":
        conditions.append(known_match)
    elif known == "foreign":
        conditions.append(f"NOT {known_match}")
    if country is not None:
        conditions.append("a.country = ?" if country_exact else "a.country LIKE ?")
        parameters.append(country if country_exact else f"%{country}%")
    for column, value in (
        ("a.ip", actor),
        ("a.provider", provider),
        ("a.asn", asn),
        ("a.city", city),
    ):
        if value is not None:
            conditions.append(f"{column} LIKE ?")
            parameters.append(f"%{value}%")
    if search is not None:
        field, term = parse_search(search)
        if not term:
            conditions.append("0")
        elif field is None:
            conditions.append("(CAST(b.burst_id AS TEXT) LIKE ? OR a.ip LIKE ? OR COALESCE(a.provider, '') LIKE ? OR COALESCE(a.asn, '') LIKE ? OR COALESCE(a.country, '') LIKE ? OR COALESCE(a.city, '') LIKE ? OR h.name LIKE ? OR b.start_time LIKE ? OR CAST((julianday(b.end_time) - julianday(b.start_time)) * 86400 AS TEXT) LIKE ? OR CAST(b.read_count + b.write_count + b.other_count AS TEXT) LIKE ? OR CAST(b.avg_count AS TEXT) LIKE ?)")
            parameters.extend([f"%{term}%"] * 11)
        elif field in {"id", "burst_id"}:
            conditions.append("CAST(b.burst_id AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "time":
            conditions.append("b.start_time LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "duration":
            conditions.append("CAST((julianday(b.end_time) - julianday(b.start_time)) * 86400 AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "requests":
            conditions.append("CAST(b.read_count + b.write_count + b.other_count AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "avg_count":
            conditions.append("CAST(b.avg_count AS TEXT) LIKE ?")
            parameters.append(f"%{term}%")
        elif field == "location":
            conditions.append("(a.country LIKE ? OR a.city LIKE ? OR a.provider LIKE ? OR a.asn LIKE ?)")
            parameters.extend([f"%{term}%"] * 4)
        elif field == "actor":
            conditions.append("(a.ip LIKE ? OR COALESCE(a.provider,'') LIKE ? OR COALESCE(a.asn,'') LIKE ? OR COALESCE(a.country,'') LIKE ? OR COALESCE(a.city,'') LIKE ?)")
            parameters.extend([f"%{term}%"] * 5)
        elif field in {"ip", "host", "country", "city", "provider", "asn"}:
            column = {"ip": "a.ip", "host": "h.name", "country": "a.country", "city": "a.city", "provider": "a.provider", "asn": "a.asn"}[field]
            conditions.append(f"COALESCE({column}, '') LIKE ?")
            parameters.append(f"%{term}%")
        else:
            conditions.append("0")
    if actor_id is not None:
        conditions.append("b.actor_id = ?")
        parameters.append(actor_id)

    where_clause = " AND ".join(conditions)
    database = get_database(request)
    from_clause = """FROM burst AS b
                     JOIN actor AS a ON a.actor_id = b.actor_id
                     LEFT JOIN host AS h ON h.host_id = b.host_id"""
    known_expression = f"CASE WHEN {known_match} THEN 1 ELSE 0 END AS known"
    filtered = f"SELECT b.*, a.ip AS actor_ip, a.country, a.provider, a.asn, a.city, a.first_time AS actor_first_time, h.name AS host, {known_expression} {from_clause} WHERE {where_clause}"

    aggregate_rows = database.query(
        f"""WITH filtered AS ({filtered})
            SELECT COUNT(*) AS burst_count,
                   COUNT(DISTINCT actor_id) AS actor_count,
                   COUNT(DISTINCT CASE WHEN actor_first_time >= ? AND actor_first_time < ? THEN actor_id END) AS new_actor_count,
                   COALESCE(SUM(read_count + write_count + other_count), 0) AS request_count,
                   COALESCE(SUM(read_count), 0) AS read_count,
                   COALESCE(SUM(write_count), 0) AS write_count,
                   COALESCE(SUM(other_count), 0) AS other_count,
                   AVG(read_count + write_count + other_count) AS avg_requests_per_burst,
                   MAX(read_count + write_count + other_count) AS max_requests_per_burst,
                   AVG((julianday(end_time) - julianday(start_time)) * 86400.0) AS avg_duration_seconds,
                   MIN((julianday(end_time) - julianday(start_time)) * 86400.0) AS min_duration_seconds,
                   MAX((julianday(end_time) - julianday(start_time)) * 86400.0) AS max_duration_seconds,
                   AVG(avg_count) AS avg_requests_per_second
            FROM filtered""",
        [*parameters, start, end],
    )
    summary = aggregate_rows[0]
    burst_count = summary["burst_count"]
    actor_count = summary["actor_count"]
    summary.update(
        {
            "avg_bursts_per_actor": burst_count / actor_count if actor_count else 0,
            "median_requests_per_burst": _median(
                database, filtered, parameters,
                "read_count + write_count + other_count",
            ),
            "median_duration_seconds": _median(
                database, filtered, parameters,
                "(julianday(end_time) - julianday(start_time)) * 86400.0",
            ),
            "median_bursts_per_actor": _median_bursts_per_actor(
                database, filtered, parameters,
            ),
            "max_bursts_per_actor": _max_bursts_per_actor(
                database, filtered, parameters,
            ),
        }
    )

    sort_expressions = {
        "burst_id": "b.burst_id",
        "start_time": "b.start_time",
        "actor_ip": "a.ip",
        "host": "h.name",
        "country": "a.country",
        "duration": "(julianday(b.end_time) - julianday(b.start_time))",
        "requests": "(b.read_count + b.write_count + b.other_count)",
        "avg_count": "b.avg_count",
    }
    order_by = f"{sort_expressions[sort_by]} {sort_order.upper()}, b.start_time DESC, b.burst_id DESC"
    items = database.query(
        f"""{filtered}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    return {
        "summary": summary,
        "items": items,
        "limit": limit,
        "offset": offset,
        "from": start,
        "to": end,
    }


@router.get("/burst_counts")
def get_burst_counts(
    request: Request,
    from_: datetime = Query(alias="from", description="Start time, inclusive (ISO 8601)"),
    to: datetime = Query(description="End time, exclusive (ISO 8601)"),
    bars: int = Query(default=24, ge=1, le=500),
    bucket_minutes: int | None = Query(default=None, ge=1, le=4320),
    bucket_anchor: datetime | None = Query(default=None),
    bucket_timezone: str | None = Query(default=None),
    include_bursts: bool = Query(default=True, description="Include burst details for dashboard tooltips"),
) -> dict[str, Any]:
    """Return all bursts grouped into the dashboard's time buckets."""
    start_dt = from_.replace(tzinfo=timezone.utc) if from_.tzinfo is None else from_.astimezone(timezone.utc)
    end_dt = to.replace(tzinfo=timezone.utc) if to.tzinfo is None else to.astimezone(timezone.utc)
    if start_dt >= end_dt:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")

    fixed_buckets: list[tuple[datetime, datetime]] = []
    if bucket_minutes is not None:
        try:
            bucket_zone = ZoneInfo(bucket_timezone) if bucket_timezone else timezone.utc
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="'bucket_timezone' must be a valid IANA timezone") from exc
        bucket_start = (bucket_anchor.replace(tzinfo=timezone.utc) if bucket_anchor and bucket_anchor.tzinfo is None else bucket_anchor.astimezone(timezone.utc) if bucket_anchor else start_dt)
        if bucket_start > start_dt:
            raise HTTPException(status_code=422, detail="'bucket_anchor' must not be later than 'from'")
        while bucket_start < end_dt:
            local_start = bucket_start.astimezone(bucket_zone)
            if bucket_minutes <= 60:
                next_bucket = bucket_start + timedelta(minutes=bucket_minutes)
            elif bucket_minutes == 480:
                if local_start.hour < 8:
                    next_date, next_hour = local_start.date(), 8
                elif local_start.hour < 16:
                    next_date, next_hour = local_start.date(), 16
                else:
                    next_date, next_hour = local_start.date() + timedelta(days=1), 0
                next_bucket = datetime.combine(next_date, time.min).replace(hour=next_hour, tzinfo=bucket_zone).astimezone(timezone.utc)
            else:
                day_count = bucket_minutes // 1440
                next_date = local_start.date() + timedelta(days=day_count)
                next_bucket = datetime.combine(next_date, time.min, tzinfo=bucket_zone).astimezone(timezone.utc)
            if next_bucket <= bucket_start:
                raise HTTPException(status_code=422, detail="Bucket interval did not advance")
            fixed_buckets.append((bucket_start, min(next_bucket, end_dt)))
            bucket_start = next_bucket
    else:
        duration = end_dt - start_dt
        total_microseconds = duration.days * 86_400_000_000 + duration.seconds * 1_000_000 + duration.microseconds
        for index in range(bars):
            bucket_start = start_dt + timedelta(microseconds=total_microseconds * index // bars)
            bucket_end = end_dt if index + 1 == bars else start_dt + timedelta(microseconds=total_microseconds * (index + 1) // bars)
            fixed_buckets.append((bucket_start, bucket_end))

    bucket_values = ", ".join("(?, ?, ?)" for _ in fixed_buckets)
    bucket_cte = f"buckets(bucket_index, start_utc, end_utc) AS (VALUES {bucket_values})"
    bucket_parameters = [value for index, (bucket_start, bucket_end) in enumerate(fixed_buckets) for value in (index, _utc_timestamp(bucket_start), _utc_timestamp(bucket_end))]
    database = get_database(request)
    if include_bursts:
        rows = database.query(
            f"""WITH {bucket_cte}
                SELECT buckets.bucket_index, bursts.burst_id, bursts.start_time, bursts.end_time,
                       bursts.avg_count, bursts.read_count, bursts.write_count, bursts.other_count,
                       actors.ip AS actor_ip, actors.provider, actors.asn, actors.city, actors.country,
                       hosts.name AS host
                FROM buckets
                LEFT JOIN burst AS bursts
                  ON bursts.start_time >= buckets.start_utc AND bursts.start_time < buckets.end_utc
                LEFT JOIN actor AS actors ON actors.actor_id = bursts.actor_id
                LEFT JOIN host AS hosts ON hosts.host_id = bursts.host_id
                ORDER BY buckets.bucket_index, bursts.start_time, bursts.burst_id""",
            bucket_parameters,
        )
    else:
        rows = database.query(
            f"""WITH {bucket_cte}
                SELECT buckets.bucket_index, COUNT(bursts.burst_id) AS burst_count
                FROM buckets
                LEFT JOIN burst AS bursts
                  ON bursts.start_time >= buckets.start_utc AND bursts.start_time < buckets.end_utc
                GROUP BY buckets.bucket_index
                ORDER BY buckets.bucket_index""",
            bucket_parameters,
        )
    items: list[dict[str, Any]] = [
        {"from": _utc_timestamp(bucket_start), "to": _utc_timestamp(bucket_end), "burst_count": 0, "bursts": []}
        for bucket_start, bucket_end in fixed_buckets
    ]
    if include_bursts:
        for row in rows:
            if row["burst_id"] is None:
                continue
            item = items[row["bucket_index"]]
            item["burst_count"] += 1
            item["bursts"].append({
                "burst_id": row["burst_id"], "start_time": row["start_time"], "end_time": row["end_time"],
                "avg_count": row["avg_count"], "read_count": row["read_count"], "write_count": row["write_count"],
                "other_count": row["other_count"], "actor_ip": row["actor_ip"], "provider": row["provider"],
                "asn": row["asn"], "city": row["city"], "country": row["country"], "host": row["host"],
            })
    else:
        for row in rows:
            items[row["bucket_index"]]["burst_count"] = row["burst_count"]
    return {"items": items, "from": _utc_timestamp(start_dt), "to": _utc_timestamp(end_dt), "bars": len(fixed_buckets)}


def _median(database: Any, filtered: str, parameters: list[Any], expression: str) -> float | None:
    """Calculate a median with SQLite window functions without loading all rows."""
    rows = database.query(
        f"""WITH filtered AS ({filtered}),
            values_to_rank AS (SELECT {expression} AS value FROM filtered),
            ranked AS (
                SELECT value, ROW_NUMBER() OVER (ORDER BY value) AS row_number,
                       COUNT(*) OVER () AS row_count
                FROM values_to_rank
            )
            SELECT AVG(value) AS median FROM ranked
            WHERE row_number IN ((row_count + 1) / 2, (row_count + 2) / 2)""",
        parameters,
    )
    return rows[0]["median"]


def _median_bursts_per_actor(
    database: Any, filtered: str, parameters: list[Any]
) -> float | None:
    """Calculate the median number of matching bursts per actor."""
    rows = database.query(
        f"""WITH filtered AS ({filtered}),
            actor_counts AS (
                SELECT actor_id, COUNT(*) AS burst_count
                FROM filtered GROUP BY actor_id
            ),
            ranked AS (
                SELECT burst_count, ROW_NUMBER() OVER (ORDER BY burst_count) AS row_number,
                       COUNT(*) OVER () AS row_count
                FROM actor_counts
            )
            SELECT AVG(burst_count) AS median FROM ranked
            WHERE row_number IN ((row_count + 1) / 2, (row_count + 2) / 2)""",
        parameters,
    )
    return rows[0]["median"]


def _max_bursts_per_actor(
    database: Any, filtered: str, parameters: list[Any]
) -> int:
    """Calculate the largest number of matching bursts for one actor."""
    rows = database.query(
        f"""WITH filtered AS ({filtered}),
            actor_counts AS (
                SELECT actor_id, COUNT(*) AS burst_count
                FROM filtered GROUP BY actor_id
            )
            SELECT COALESCE(MAX(burst_count), 0) AS maximum FROM actor_counts""",
        parameters,
    )
    return rows[0]["maximum"]
