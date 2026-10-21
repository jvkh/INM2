"""Maintenance exclusion controls."""

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel

from api.dependencies import get_database

router = APIRouter()


class ExclusionUpdate(BaseModel):
    excluded: bool


@router.get("/maintenance/exclusions/{ip}")
def get_exclusion(request: Request, ip: str = Path(min_length=1, max_length=64)) -> dict[str, object]:
    """Return whether an IP is protected from inactivity cleanup."""
    database = get_database(request)
    rows = database.query("SELECT 1 FROM maintenance_exclusion WHERE ip = ?", (ip,))
    return {"ip": ip, "excluded": bool(rows)}


@router.put("/maintenance/exclusions/{ip}")
def set_exclusion(request: Request, body: ExclusionUpdate, ip: str = Path(min_length=1, max_length=64)) -> dict[str, object]:
    """Protect or unprotect one source IP across all cleanup targets."""
    if any(character.isspace() for character in ip):
        raise HTTPException(status_code=422, detail="IP must not contain whitespace")
    database = get_database(request)
    with database.transaction() as connection:
        if body.excluded:
            connection.execute("INSERT OR IGNORE INTO maintenance_exclusion(ip) VALUES (?)", (ip,))
        else:
            connection.execute("DELETE FROM maintenance_exclusion WHERE ip = ?", (ip,))
    return {"ip": ip, "excluded": body.excluded}
