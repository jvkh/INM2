"""Cowrie SSH event browsing and correlation endpoints."""

import os
import struct
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database
from common.cowrie_analysis import classify_command
from common.status import CollectorStatus

router = APIRouter()

_TTY_RECORD = struct.Struct("<iLiiLL")
_TTY_MAX_BYTES = 8 * 1024 * 1024


def _tty_filename(extra_json: str | None) -> str | None:
    if not extra_json:
        return None
    try:
        import json

        value = json.loads(extra_json).get("ttylog")
    except (ValueError, AttributeError, TypeError):
        return None
    if not isinstance(value, str):
        return None
    # Cowrie records paths such as var/lib/cowrie/tty/<hash>. Only take the
    # final filename; the API never follows an event-provided directory path.
    name = Path(value).name
    if not name or name in {".", ".."} or not all(c.isalnum() or c in "._-" for c in name):
        return None
    return name


def _tty_file(filename: str) -> Path:
    root = Path(os.environ.get("COWRIE_TTY_DIR", "/cowrie-tty")).resolve()
    path = (root / filename).resolve()
    if path.parent != root:
        raise ValueError("Invalid TTY recording path")
    return path


def _group_tty_recordings(database: Any, src_ip: str | None, first_time: str, last_time: str) -> list[dict[str, str]]:
    rows = database.query(
        """SELECT e.event_id, e.session, e.extra_json FROM cowrie_event e
           WHERE e.session IN (SELECT DISTINCT session FROM cowrie_event
                               WHERE src_ip IS ? AND julianday(time) >= julianday(?)
                                 AND julianday(time) <= julianday(?) AND session IS NOT NULL)
             AND e.event_type IN ('cowrie.log.open', 'cowrie.log.closed')
           ORDER BY e.time DESC, e.event_id DESC""",
        (src_ip, first_time, last_time),
    )
    recordings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        filename = _tty_filename(row["extra_json"])
        if not filename:
            continue
        recording_key = (row["session"], filename)
        if recording_key in seen:
            continue
        try:
            if not _tty_file(filename).is_file():
                continue
        except (OSError, ValueError):
            continue
        seen.add(recording_key)
        recordings.append({"event_id": row["event_id"], "session": row["session"], "filename": filename})
    return recordings


def _read_ttylog(path: Path) -> dict[str, Any]:
    """Read complete Cowrie UML records, tolerating a partial trailing write."""
    records: list[tuple[int, bytes]] = []
    consumed = 0
    closed = False
    with path.open("rb") as stream:
        while consumed + _TTY_RECORD.size <= _TTY_MAX_BYTES:
            header = stream.read(_TTY_RECORD.size)
            if len(header) < _TTY_RECORD.size:
                break
            op, _tty, length, direction, _sec, _usec = _TTY_RECORD.unpack(header)
            if length < 0 or length > _TTY_MAX_BYTES or op not in {1, 2, 3, 4}:
                raise ValueError("Invalid Cowrie TTY record")
            data = stream.read(length)
            if len(data) < length:
                break
            consumed += _TTY_RECORD.size + length
            if op == 3 and data:
                records.append((direction, data))
            if op == 2:
                closed = True
                break
    first_direction = next((direction for direction, _ in records if direction != 3), 0)
    output_direction = 2 if first_direction == 1 else first_direction
    chunks = []
    for direction, data in records:
        kind = "command" if direction == 3 else ("output" if direction == output_direction else "input")
        chunks.append({"kind": kind, "text": data.decode("utf-8", errors="replace")})
    return {"chunks": chunks, "complete": closed, "bytes_read": consumed}


def _enabled() -> bool:
    return os.environ.get("COWRIE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_enabled(request: Request) -> None:
    enabled = _enabled()
    try:
        environment = CollectorStatus.read_snapshot(get_database(request)).get("environment", {})
        enabled = enabled or str(environment.get("COWRIE_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        pass
    if not enabled:
        raise HTTPException(status_code=404, detail="Cowrie is not enabled")


@router.get("/cowrie/summary")
def summary(request: Request, from_: datetime = Query(alias="from"), to: datetime = Query()) -> dict[str, int]:
    _require_enabled(request)
    start, end = _time(from_), _time(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    row = get_database(request).query(
        """SELECT COUNT(*) AS event_count,
                  COUNT(DISTINCT NULLIF(src_ip, '')) AS actor_count,
                  COUNT(DISTINCT NULLIF(session, '')) AS session_count,
                  SUM(CASE WHEN event_type LIKE '%login.failed%' THEN 1 ELSE 0 END) AS failed_login_count,
                  SUM(CASE WHEN event_type = 'cowrie.command.input' AND COALESCE(TRIM(input), '') <> '' THEN 1 ELSE 0 END) AS command_count
           FROM cowrie_event WHERE julianday(time) >= julianday(?) AND julianday(time) < julianday(?)""", (start, end)
    )[0]
    return {key: int(row[key] or 0) for key in ("event_count", "actor_count", "session_count", "failed_login_count", "command_count")}


@router.get("/cowrie/events")
def events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=300),
    event_type: str | None = Query(default=None, min_length=1, max_length=100),
    sort_by: Literal["time", "src_ip", "event_type", "username"] = Query(default="time"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> dict[str, Any]:
    _require_enabled(request)
    database = get_database(request)
    conditions: list[str] = []
    parameters: list[Any] = []
    if from_:
        conditions.append("julianday(e.time) >= julianday(?)"); parameters.append(_time(from_))
    if to:
        conditions.append("julianday(e.time) < julianday(?)"); parameters.append(_time(to))
    if from_ and to and _time(from_) >= _time(to):
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    if event_type:
        conditions.append("e.event_type = ?"); parameters.append(event_type)
    if search:
        term = f"%{search.strip()}%"
        searchable = ("e.src_ip", "e.session", "e.event_type", "e.username", "e.password", "e.input", "e.message", "e.sensor")
        conditions.append("(" + " OR ".join(f"COALESCE({column}, '') LIKE ?" for column in searchable) + ")")
        parameters.extend([term] * len(searchable))
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    total = database.query(f"SELECT COUNT(*) AS total FROM cowrie_event e {where}", parameters)[0]["total"]
    sort_columns = {"time": "e.time", "src_ip": "e.src_ip", "event_type": "e.event_type", "username": "e.username"}
    items = database.query(
        f"""SELECT e.event_id, e.time, e.src_ip, e.session, e.event_type,
                   e.username, e.password, e.input, e.message, e.sensor,
                   e.provider, e.asn, e.country, e.city, e.extra_json
            FROM cowrie_event e {where}
            ORDER BY {sort_columns[sort_by]} {sort_order.upper()}, e.event_id {sort_order.upper()}
            LIMIT ? OFFSET ?""",
        [*parameters, limit, offset],
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/cowrie/groups")
def groups(
    request: Request,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, min_length=1, max_length=300),
    event_type: str | None = Query(default=None, min_length=1, max_length=100),
    protected_only: bool = Query(default=False, description="Only actors protected from inactivity cleanup"),
) -> dict[str, Any]:
    """Group events from one source IP into five-minute sessions."""
    _require_enabled(request)
    database = get_database(request)
    conditions: list[str] = []
    parameters: list[Any] = []
    if from_:
        conditions.append("julianday(e.time) >= julianday(?)"); parameters.append(_time(from_))
    if to:
        conditions.append("julianday(e.time) < julianday(?)"); parameters.append(_time(to))
    if from_ and to and _time(from_) >= _time(to):
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    if event_type:
        conditions.append("e.event_type = ?"); parameters.append(event_type)
    if protected_only:
        conditions.append("EXISTS (SELECT 1 FROM maintenance_exclusion AS me WHERE me.ip = e.src_ip)")
    if search:
        term = f"%{search.strip()}%"
        columns = ("e.src_ip", "e.session", "e.event_type", "e.username", "e.password", "e.input", "e.message", "e.sensor")
        conditions.append("(" + " OR ".join(f"COALESCE({column}, '') LIKE ?" for column in columns) + ")")
        parameters.extend([term] * len(columns))
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cte = f"""WITH filtered AS (
        SELECT e.*, LAG(julianday(e.time)) OVER (PARTITION BY e.src_ip ORDER BY e.time, e.event_id) AS prev_time
        FROM cowrie_event e {where}
    ), marked AS (
        SELECT *, SUM(CASE WHEN prev_time IS NULL OR (julianday(time)-prev_time)*86400 > 300 THEN 1 ELSE 0 END)
          OVER (PARTITION BY src_ip ORDER BY time, event_id) AS session_group FROM filtered
    ), grouped AS (
        SELECT src_ip, session_group, MIN(time) AS first_time, MAX(time) AS last_time,
          COUNT(*) AS event_count, SUM(CASE WHEN event_type LIKE '%login.failed%' THEN 1 ELSE 0 END) AS failed_login_count,
          SUM(CASE WHEN event_type = 'cowrie.command.input' AND COALESCE(TRIM(input), '') <> '' THEN 1 ELSE 0 END) AS command_count,
          MAX(provider) AS provider, MAX(asn) AS asn, MAX(country) AS country, MAX(city) AS city
        FROM marked GROUP BY src_ip, session_group
    )"""
    total = database.query(f"{cte} SELECT COUNT(*) AS total FROM grouped", parameters)[0]["total"]
    rows = database.query(
        f"{cte} SELECT * FROM grouped ORDER BY last_time DESC, src_ip LIMIT ? OFFSET ?",
        [*parameters, limit, offset],
    )
    for row in rows:
        recordings = _group_tty_recordings(database, row["src_ip"], row["first_time"], row["last_time"])
        row["tty_recording_count"] = len(recordings)
    return {"items": rows, "total": total, "limit": limit, "offset": offset, "session_gap_seconds": 300}


@router.get("/cowrie/group-events")
def group_events(
    request: Request,
    src_ip: str = Query(min_length=1, max_length=64),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    search: str | None = Query(default=None, min_length=1, max_length=300),
    event_type: str | None = Query(default=None, min_length=1, max_length=100),
) -> dict[str, Any]:
    _require_enabled(request)
    start, end = _time(from_), _time(to)
    conditions = ["e.src_ip IS ?", "julianday(e.time)>=julianday(?)", "julianday(e.time)<=julianday(?)"]
    parameters: list[Any] = [src_ip, start, end]
    if event_type:
        conditions.append("e.event_type = ?"); parameters.append(event_type)
    if search:
        term = f"%{search.strip()}%"
        columns = ("e.src_ip", "e.session", "e.event_type", "e.username", "e.password", "e.input", "e.message", "e.sensor")
        conditions.append("(" + " OR ".join(f"COALESCE({column}, '') LIKE ?" for column in columns) + ")")
        parameters.extend([term] * len(columns))
    rows = get_database(request).query(
        f"""SELECT e.* FROM cowrie_event e WHERE {' AND '.join(conditions)}
           ORDER BY e.time DESC, e.event_id DESC""",
        parameters,
    )
    return {"items": rows, "total": len(rows)}


@router.get("/cowrie/group-commands")
def group_commands(
    request: Request,
    src_ip: str = Query(min_length=1, max_length=64),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
) -> dict[str, Any]:
    """Return grouped and classified shell commands for one Cowrie session group."""
    _require_enabled(request)
    start, end = _time(from_), _time(to)
    if start > end:
        raise HTTPException(status_code=422, detail="'from' must not be later than 'to'")
    database = get_database(request)
    command_total = database.query(
        """SELECT COUNT(*) AS total FROM (
             SELECT lower(trim(input)) FROM cowrie_event WHERE src_ip=?
               AND julianday(time)>=julianday(?) AND julianday(time)<=julianday(?)
               AND event_type='cowrie.command.input' AND COALESCE(trim(input),'')<>''
             GROUP BY lower(trim(input)))""",
        (src_ip, start, end),
    )[0]["total"]
    commands = database.query(
        """SELECT lower(trim(input)) AS normalized_command, MIN(trim(input)) AS command,
                  COUNT(*) AS occurrences, COUNT(DISTINCT session) AS session_count,
                  MIN(time) AS first_time, MAX(time) AS last_time
           FROM cowrie_event WHERE src_ip=? AND julianday(time)>=julianday(?)
             AND julianday(time)<=julianday(?) AND event_type='cowrie.command.input'
             AND COALESCE(trim(input),'')<>''
           GROUP BY lower(trim(input)) ORDER BY occurrences DESC, normalized_command LIMIT 100""",
        (src_ip, start, end),
    )
    for command in commands:
        command["category"] = classify_command(command["command"])
    sequence_rows = database.query(
        """SELECT session, input, time FROM cowrie_event WHERE src_ip=?
           AND julianday(time)>=julianday(?) AND julianday(time)<=julianday(?)
           AND event_type='cowrie.command.input' AND session IS NOT NULL
           AND COALESCE(trim(input),'')<>''
           ORDER BY session, julianday(time), event_id LIMIT 10000""",
        (src_ip, start, end),
    )
    per_session: dict[str, list[dict[str, str]]] = {}
    for row in sequence_rows:
        sequence = per_session.setdefault(row["session"], [])
        if len(sequence) < 20:
            sequence.append({"command": row["input"].strip(), "time": row["time"]})
    grouped_sequences: dict[tuple[str, ...], dict[str, Any]] = {}
    for sequence in per_session.values():
        if not sequence:
            continue
        signature = tuple(item["command"].lower() for item in sequence)
        grouped = grouped_sequences.get(signature)
        if grouped is None:
            grouped_sequences[signature] = {
                "commands": [item["command"] for item in sequence], "session_count": 1,
                "first_time": sequence[0]["time"], "last_time": sequence[-1]["time"],
            }
        else:
            grouped["session_count"] += 1
            grouped["first_time"] = min(grouped["first_time"], sequence[0]["time"])
            grouped["last_time"] = max(grouped["last_time"], sequence[-1]["time"])
    sequences = sorted(grouped_sequences.values(), key=lambda item: (-item["session_count"], item["commands"]))[:50]
    return {
        "src_ip": src_ip,
        "from": start,
        "to": end,
        "commands": commands,
        "command_total": int(command_total),
        "command_sequences": sequences,
        "command_sequence_total": len(grouped_sequences),
        "command_sequences_truncated": len(sequence_rows) >= 10000 or len(grouped_sequences) > 50,
    }


@router.get("/cowrie/groups/tty")
def group_tty_recordings(
    request: Request,
    src_ip: str = Query(min_length=1, max_length=64),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    distinct: bool = Query(default=False, description="Group recordings with identical terminal content"),
) -> dict[str, Any]:
    """Read one page of TTY recordings, optionally grouped by identical content."""
    _require_enabled(request)
    start, end = _time(from_), _time(to)
    if start > end:
        raise HTTPException(status_code=422, detail="'from' must not be later than 'to'")
    database = get_database(request)
    recordings = _group_tty_recordings(database, src_ip, start, end)
    if distinct:
        unique: dict[str, dict[str, Any]] = {}
        for recording in recordings:
            try:
                content = _read_ttylog(_tty_file(recording["filename"]))
            except (OSError, ValueError, struct.error):
                continue
            signature = "".join(chunk["text"] for chunk in content["chunks"])
            if signature in unique:
                unique[signature]["occurrences"] += 1
            else:
                unique[signature] = {"event_id": recording["event_id"], "occurrences": 1, **content}
        distinct_items = list(unique.values())
        return {"items": distinct_items[offset:offset + limit], "total": len(distinct_items), "limit": limit, "offset": offset, "distinct": True}

    items = []
    for recording in recordings[offset:offset + limit]:
        try:
            content = _read_ttylog(_tty_file(recording["filename"]))
        except (OSError, ValueError, struct.error):
            continue
        items.append({"event_id": recording["event_id"], "session": recording["session"], "occurrences": 1, **content})
    return {"items": items, "total": len(recordings), "limit": limit, "offset": offset, "distinct": False}


@router.get("/cowrie/events/{event_id}/tty")
def session_tty(event_id: str, request: Request) -> dict[str, Any]:
    """Return the currently available TTY recording for this event's session."""
    _require_enabled(request)
    database = get_database(request)
    selected = database.query(
        "SELECT session FROM cowrie_event WHERE event_id = ? LIMIT 1", (event_id,)
    )
    if not selected or not selected[0]["session"]:
        raise HTTPException(status_code=404, detail="Cowrie session not found")
    session = selected[0]["session"]
    recording_events = database.query(
        """SELECT extra_json FROM cowrie_event
           WHERE session = ? AND event_type IN ('cowrie.log.open', 'cowrie.log.closed')
           ORDER BY time DESC, event_id DESC""", (session,)
    )
    filename = None
    for row in recording_events:
        filename = _tty_filename(row["extra_json"])
        if filename:
            break
    if not filename:
        return {"available": False, "complete": False, "chunks": [], "bytes_read": 0}
    try:
        path = _tty_file(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid TTY recording path")
    if not path.is_file():
        return {"available": False, "complete": False, "chunks": [], "bytes_read": 0}
    try:
        result = _read_ttylog(path)
    except (OSError, ValueError, struct.error) as exc:
        raise HTTPException(status_code=422, detail="Cowrie TTY recording could not be read") from exc
    return {"available": True, **result}


@router.delete("/cowrie/groups")
def delete_group(
    request: Request,
    src_ip: str = Query(min_length=1, max_length=64),
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
) -> dict[str, int]:
    """Delete Cowrie events in one displayed actor/time group."""
    _require_enabled(request)
    start, end = _time(from_), _time(to)
    if start > end:
        raise HTTPException(status_code=422, detail="'from' must not be later than 'to'")
    database = get_database(request)
    with database.transaction() as connection:
        cursor = connection.execute(
            """DELETE FROM cowrie_event
               WHERE src_ip=? AND julianday(time)>=julianday(?) AND julianday(time)<=julianday(?)""",
            (src_ip, start, end),
        )
        deleted_count = cursor.rowcount
    return {"deleted_count": deleted_count}


@router.get("/cowrie/statistics")
def statistics(request: Request, from_: datetime = Query(alias="from"), to: datetime = Query()) -> dict[str, Any]:
    _require_enabled(request)
    start, end = _time(from_), _time(to)
    if start >= end:
        raise HTTPException(status_code=422, detail="'from' must be earlier than 'to'")
    database = get_database(request)
    rows = database.query(
        """SELECT event_type AS name, COUNT(*) AS event_count
           FROM cowrie_event WHERE julianday(time) >= julianday(?) AND julianday(time) < julianday(?)
           GROUP BY event_type ORDER BY event_count DESC, name""", (start, end)
    )
    total = sum(row["event_count"] for row in rows)
    by_type = [{**row, "share_percent": round(row["event_count"] * 100 / total, 2) if total else 0} for row in rows]
    counts = database.query(
        """SELECT COUNT(*) AS event_count, COUNT(DISTINCT src_ip) AS actor_count,
                  COUNT(DISTINCT session) AS session_count,
                  SUM(CASE WHEN event_type LIKE '%login.failed%' THEN 1 ELSE 0 END) AS failed_login_count,
                  SUM(CASE WHEN event_type = 'cowrie.command.input' AND COALESCE(TRIM(input), '') <> '' THEN 1 ELSE 0 END) AS command_count
           FROM cowrie_event WHERE julianday(time) >= julianday(?) AND julianday(time) < julianday(?)""", (start, end)
    )[0]
    return {**{key: int(counts[key] or 0) for key in ("event_count", "actor_count", "session_count", "failed_login_count", "command_count")}, "by_type": by_type}
