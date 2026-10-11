"""Read settings grouped by their group name."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.dependencies import get_database


router = APIRouter()


@router.get("/params")
def get_params(
    request: Request,
    group_name: str = Query(min_length=1),
    name: str | None = Query(default=None, min_length=1),
) -> dict[str, Any]:
    """Return one setting or all settings for a required group."""
    database = get_database(request)
    if name is not None:
        rows = database.query(
            """SELECT group_name, name, value
               FROM settings
               WHERE group_name = ? AND name = ?""",
            (group_name, name),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Parameter not found")
        return rows[0]

    rows = database.query(
        """SELECT name, value
           FROM settings
           WHERE group_name = ?
           ORDER BY name""",
        (group_name,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Parameter group not found")
    return {"group_name": group_name, "items": rows}


@router.put("/params")
def put_param(
    request: Request,
    group_name: str = Query(min_length=1),
    name: str = Query(min_length=1),
    value: str | None = Query(default=None),
) -> dict[str, Any]:
    """Upsert one setting, or delete it when value is omitted."""
    database = get_database(request)
    if value is None:
        database.execute(
            "DELETE FROM settings WHERE group_name = ? AND name = ?",
            (group_name, name),
        )
        return {"group_name": group_name, "name": name, "deleted": True}

    database.execute(
        """INSERT INTO settings (group_name, name, value) VALUES (?, ?, ?)
           ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value""",
        (group_name, name, value),
    )
    return {"group_name": group_name, "name": name, "value": value, "deleted": False}
