"""New request and burst notifications backed by a persistent settings cursor."""

from typing import Any

from fastapi import APIRouter, Query, Request

from api.dependencies import get_database

router = APIRouter()
_GROUP = "notifications"


def _cursor(database: Any, name: str, current: int) -> int:
    rows = database.query(
        "SELECT value FROM settings WHERE group_name = ? AND name = ?",
        (_GROUP, name),
    )
    if rows:
        try:
            return max(0, int(rows[0]["value"] or 0))
        except (TypeError, ValueError):
            pass
    database.execute(
        "INSERT INTO settings (group_name, name, value) VALUES (?, ?, ?) "
        "ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value",
        (_GROUP, name, str(current)),
    )
    return current


@router.get("/notifications")
def get_notifications(request: Request) -> dict[str, Any]:
    """Return additions since the persisted seen cursors."""
    database = get_database(request)
    request_max = int(database.query("SELECT COALESCE(MAX(request_id), 0) AS value FROM request")[0]["value"])
    burst_max = int(database.query("SELECT COALESCE(MAX(burst_id), 0) AS value FROM burst")[0]["value"])
    request_cursor = _cursor(database, "request_cursor", request_max)
    burst_cursor = _cursor(database, "burst_cursor", burst_max)
    requests = database.query(
        """SELECT r.request_id, r.start_utc, a.ip AS actor_ip, h.name AS host,
                  r.request_method, r.request_path, r.downstream_status
           FROM request AS r JOIN actor AS a ON a.actor_id = r.actor_id
           LEFT JOIN host AS h ON h.host_id = r.host_id
           WHERE r.request_id > ? ORDER BY r.request_id DESC LIMIT 5""",
        (request_cursor,),
    )
    bursts = database.query(
        """SELECT b.burst_id, b.start_time, a.ip AS actor_ip, h.name AS host,
                  b.read_count + b.write_count + b.other_count AS request_count
           FROM burst AS b JOIN actor AS a ON a.actor_id = b.actor_id
           LEFT JOIN host AS h ON h.host_id = b.host_id
           WHERE b.burst_id > ? ORDER BY b.burst_id DESC LIMIT 5""",
        (burst_cursor,),
    )
    request_count = database.query("SELECT COUNT(*) AS value FROM request WHERE request_id > ?", (request_cursor,))[0]["value"]
    burst_count = database.query("SELECT COUNT(*) AS value FROM burst WHERE burst_id > ?", (burst_cursor,))[0]["value"]
    return {
        "request_count": request_count,
        "burst_count": burst_count,
        "requests": requests,
        "bursts": bursts,
        "request_cursor": request_max,
        "burst_cursor": burst_max,
    }


@router.put("/notifications/seen")
def mark_notifications_seen(
    request: Request,
    request_cursor: int = Query(ge=0),
    burst_cursor: int = Query(ge=0),
) -> dict[str, bool]:
    """Persist the latest cursors acknowledged by the single user."""
    database = get_database(request)
    for name, value in (("request_cursor", request_cursor), ("burst_cursor", burst_cursor)):
        database.execute(
            "INSERT INTO settings (group_name, name, value) VALUES (?, ?, ?) "
            "ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value",
            (_GROUP, name, str(value)),
        )
    return {"saved": True}
