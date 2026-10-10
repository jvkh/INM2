"""Local IP geolocation lookups using MaxMind GeoLite2 MMDB files."""

from __future__ import annotations

import ipaddress
import logging
from pathlib import Path
from typing import Any

from common.env import EnvConfig

logger = logging.getLogger(__name__)


class GeoLocator:
    """Resolve public IPs to country, city, ASN, and network organization."""

    def __init__(self, config: EnvConfig) -> None:
        self._city_reader: Any | None = None
        self._asn_reader: Any | None = None
        self._cache: dict[str, dict[str, str | None]] = {}

        city_path = config.get("GEOLITE_CITY_DB")
        asn_path = config.get("GEOLITE_ASN_DB")
        configured_paths = [Path(path) for path in (city_path, asn_path) if path]
        if not configured_paths:
            return

        if not any(path.is_file() for path in configured_paths):
            logger.warning("No GeoLite database files found; IP geolocation is disabled")
            return

        try:
            from geoip2.database import Reader
        except ImportError:
            logger.warning("geoip2 is not installed; IP geolocation is disabled")
            return

        if city_path:
            self._city_reader = self._open_reader(Reader, Path(city_path), "City")
        if asn_path:
            self._asn_reader = self._open_reader(Reader, Path(asn_path), "ASN")

    @property
    def enabled(self) -> bool:
        return self._city_reader is not None or self._asn_reader is not None

    @staticmethod
    def _open_reader(reader_type: Any, path: Path, label: str) -> Any | None:
        if not path.is_file():
            logger.warning("GeoLite %s database not found at %s", label, path)
            return None
        try:
            return reader_type(str(path))
        except Exception:
            logger.exception("Could not open GeoLite %s database at %s", label, path)
            return None

    def lookup(self, ip: str) -> dict[str, str | None]:
        """Return available location and network fields for a public IP."""
        if ip in self._cache:
            return self._cache[ip]
        result: dict[str, str | None] = {
            "provider": None,
            "asn": None,
            "city": None,
            "country": None,
        }
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            self._cache[ip] = result
            return result
        if not address.is_global:
            self._cache[ip] = result
            return result

        if self._city_reader is not None:
            try:
                response = self._city_reader.city(address)
                result["city"] = response.city.name
                result["country"] = response.country.name or response.registered_country.name
            except Exception as exc:
                logger.debug("No GeoLite City result for %s: %s", ip, exc)

        if self._asn_reader is not None:
            try:
                response = self._asn_reader.asn(address)
                if response.autonomous_system_number is not None:
                    result["asn"] = f"AS{response.autonomous_system_number}"
                result["provider"] = response.autonomous_system_organization
            except Exception as exc:
                logger.debug("No GeoLite ASN result for %s: %s", ip, exc)

        self._cache[ip] = result
        return result

    def close(self) -> None:
        """Close the loaded MMDB readers."""
        for reader in (self._city_reader, self._asn_reader):
            if reader is not None:
                reader.close()
