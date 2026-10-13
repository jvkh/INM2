"""Helpers for field-qualified free-text searches."""

from __future__ import annotations

from typing import TypeAlias

SearchField: TypeAlias = str | None

# Search aliases are deliberately independent of the selected UI language. Keep
# the matching aliases in UI/src/App.tsx in sync for the client-side global search.
_SEARCH_FIELDS = {
    "ip": "ip",
    "actor": "ip",
    "akteur": "ip",
    "host": "host",
    "country": "country",
    "land": "country",
    "city": "city",
    "stadt": "city",
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
