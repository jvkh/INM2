"""Environment-based configuration for the Internet Noise Monitor."""

from __future__ import annotations

import os
from collections.abc import Mapping


class EnvConfig:
    """Read configuration from environment variables with sensible defaults.

    Pass a mapping as ``environ`` to make configuration deterministic in other
    contexts; by default values are read from :data:`os.environ`.
    """

    DEFAULTS: dict[str, str] = {
        "LOG_FILES": "",
        "INPUT_INTERVAL_SECONDS": "3600",
        "INPUT_SAVE_MARGIN_CHARACTERS": "4096",
        "MAINTENANCE_INTERVAL_DAYS": "1",
        "MAINTENANCE_INACTIVE_DAYS": "90",
        "BURST_MAX_GAP_SECONDS": "5",
        "BURST_MIN_REQUESTS": "5",
        "BURST_WINDOW_SECONDS": "60",
        "GEOLITE_CITY_DB": "/geoip/GeoLite2-City.mmdb",
        "GEOLITE_ASN_DB": "/geoip/GeoLite2-ASN.mmdb",
        "IGNORE_REQUEST_ROUTES": "",
    }

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def get(self, name: str, default: str | None = None) -> str | None:
        """Return a variable, using its configured or supplied default.

        An unset or empty variable is treated as missing. Unknown variables
        return ``None`` unless the caller supplies ``default``.
        """
        fallback = self.DEFAULTS.get(name) if default is None else default
        value = self._environ.get(name)
        return value if value else fallback

    def get_int(self, name: str, default: int | None = None) -> int:
        """Return a variable as an integer, or raise ``ValueError`` if invalid."""
        fallback = self.DEFAULTS.get(name) if default is None else str(default)
        value = self.get(name, fallback)
        if value is None:
            raise KeyError(f"No environment variable or default configured for {name}")
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"Environment variable {name} must be an integer: {value!r}") from exc

    def get_list(self, name: str, default: str | None = None) -> list[str]:
        """Return a semicolon-separated variable as a list of non-empty values."""
        value = self.get(name, default)
        if value is None:
            return []
        return [item.strip() for item in value.split(";") if item.strip()]

    def as_dict(self) -> dict[str, str]:
        """Return all supported application variables with their effective values."""
        return {
            name: self.get(name, default) or ""
            for name, default in self.DEFAULTS.items()
        }

    @property
    def log_files(self) -> list[str]:
        return self.get_list("LOG_FILES")

    @property
    def input_interval_seconds(self) -> int:
        return self.get_int("INPUT_INTERVAL_SECONDS")

    @property
    def input_save_margin_characters(self) -> int:
        return self.get_int("INPUT_SAVE_MARGIN_CHARACTERS")

    @property
    def maintenance_interval_days(self) -> int:
        return self.get_int("MAINTENANCE_INTERVAL_DAYS")

    @property
    def maintenance_inactive_days(self) -> int:
        return self.get_int("MAINTENANCE_INACTIVE_DAYS")

    @property
    def burst_max_gap_seconds(self) -> int:
        return self.get_int("BURST_MAX_GAP_SECONDS")

    @property
    def burst_min_requests(self) -> int:
        return self.get_int("BURST_MIN_REQUESTS")

    @property
    def burst_window_seconds(self) -> int:
        return self.get_int("BURST_WINDOW_SECONDS")

    @property
    def ignore_request_routes(self) -> list[str]:
        return self.get_list("IGNORE_REQUEST_ROUTES")
