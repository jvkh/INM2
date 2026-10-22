"""Helpers for field-qualified free-text searches."""

from __future__ import annotations

from typing import TypeAlias

SearchField: TypeAlias = str | None

# Aliases cover both locale labels so saved or pasted searches work regardless
# of the currently selected interface language. The global search has its own
# smaller set because it searches a different collection of entities.
_SEARCH_FIELDS = {
    # Aliases cover the visible German and English table headings. The APIs
    # interpret generic fields such as "id" in the context of the current page.
    "id": "id",
    "incident-id": "incident_id",
    "incident id": "incident_id",
    "vorfall-id": "incident_id",
    "vorfall id": "incident_id",
    "burst-id": "burst_id",
    "burst id": "burst_id",
    "start time": "time",
    "startzeit": "time",
    "date": "time",
    "datum": "time",
    "request path": "path",
    "request-pfad": "path",
    "response status": "status",
    "antwortstatus": "status",
    "http status": "status",
    "response size": "response_size",
    "antwortgröße": "response_size",
    "body size": "request_body_size",
    "body-size": "request_body_size",
    "body-größe": "request_body_size",
    "bodygröße": "request_body_size",
    "request body": "request_body_size",
    "request body size": "request_body_size",
    "request-body-größe": "request_body_size",
    "requests/s": "avg_count",
    "requests per second": "avg_count",
    "durchschnitt requests/s": "avg_count",
    "https": "https_count",
    "http": "http_count",
    "ip": "ip",
    "ip-adresse": "ip",
    "ip address": "ip",
    "actor": "actor",
    "akteur": "actor",
    "host": "host",
    "hostname": "host",
    "country": "country",
    "land": "country",
    "city": "city",
    "stadt": "city",
    "location": "location",
    "standort": "location",
    "provider": "provider",
    "anbieter": "provider",
    "asn": "asn",
    "path": "path",
    "pfad": "path",
    "category": "category",
    "kategorie": "category",
    "method": "method",
    "methode": "method",
    "status": "status",
    "scheme": "scheme",
    "protokoll": "scheme",
    "ua": "user_agent",
    "user-agent": "user_agent",
    "user_agent": "user_agent",
    "user agent": "user_agent",
    "duration": "duration",
    "dauer": "duration",
    "time span": "time",
    "zeitspanne": "time",
    "time": "time",
    "zeit": "time",
    "first seen": "first_seen",
    "zuerst gesehen": "first_seen",
    "last seen": "last_seen",
    "zuletzt gesehen": "last_seen",
    "requests": "requests",
    "request count": "requests",
    "requestzahl": "requests",
    "requests per burst": "avg_requests_per_burst",
    "ø requests/burst": "avg_requests_per_burst",
    "read": "read_count",
    "lesend": "read_count",
    "write": "write_count",
    "schreibend": "write_count",
    "other": "other_count",
    "sonstige": "other_count",
    "indicator": "indicators",
    "indicators": "indicators",
    "indikator": "indicators",
    "indikatoren": "indicators",
    "incident type": "incident_type",
    "vorfallstyp": "incident_type",
    "state": "state",
    "vorfallstatus": "state",
    "avg. requests/s": "avg_count",
    "ø requests/s": "avg_count",
    "traffic share": "traffic_share",
    "traffic-anteil": "traffic_share",
    "https share": "https_share",
    "https-anteil": "https_share",
}


def parse_search(value: str | None) -> tuple[SearchField, str]:
    """Split a recognized ``field:value`` query, leaving plain text unchanged."""
    if value is None:
        return None, ""
    field, separator, term = value.partition(":")
    normalized_field = _SEARCH_FIELDS.get(field.strip().lower()) if separator else None
    if normalized_field is None:
        return None, value.strip()
    return normalized_field, term.strip()
