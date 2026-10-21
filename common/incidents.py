"""Shared helpers for incident-related request filtering."""

from typing import Any


def incident_request_condition(request_alias: str = "r") -> str:
    """Return SQL matching a request to its explicit incident membership."""
    return f"""EXISTS (
        SELECT 1 FROM incident_request AS ir
        WHERE ir.incident_id = ? AND ir.request_id = {request_alias}.request_id
    )"""


def incident_request_parameters(incident_id: int) -> tuple[int]:
    """Return bound values for :func:`incident_request_condition`."""
    return (incident_id,)


def attach_incident_types(database: Any, incidents: list[dict[str, Any]]) -> None:
    """Attach every detector criterion represented by each combined incident."""
    incident_ids = [item.get("incident_id") for item in incidents if item.get("incident_id") is not None]
    if not incident_ids:
        return
    placeholders = ",".join("?" for _ in incident_ids)
    rows = database.query(
        f"SELECT incident_id, incident_type FROM incident_criterion WHERE incident_id IN ({placeholders}) ORDER BY incident_type",
        incident_ids,
    )
    by_incident: dict[int, set[str]] = {}
    for row in rows:
        by_incident.setdefault(row["incident_id"], set()).add(row["incident_type"])
    for item in incidents:
        primary = item.get("incident_type")
        criteria = by_incident.get(item.get("incident_id"), set())
        if primary:
            criteria.add(primary)
            item["incident_types"] = [primary, *sorted(criteria - {primary})]
        else:
            item["incident_types"] = sorted(criteria)
