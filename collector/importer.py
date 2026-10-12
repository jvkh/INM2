"""Dispatch configured logs to readers and persist parsed requests."""

from __future__ import annotations

import logging
import ipaddress
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlsplit

from common.database import Database
from common.env import EnvConfig
from collector.geolocation import GeoLocator
from collector.traefik_reader import TraefikReader

logger = logging.getLogger(__name__)


class Importer:
    """Import log records, classify requests, and keep burst summaries current."""

    READ_METHODS = {"GET", "HEAD", "OPTIONS"}
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    CATEGORY_PATTERNS = {
        "sensible Dateien": re.compile(
            r"(?:^|/)(?:\.env(?:\.[^/]*)?|\.git(?:/|$)|\.svn(?:/|$)|"
            r"\.htaccess|\.htpasswd|\.ds_store|id_rsa|authorized_keys|"
            r"wp-config\.php|config(?:uration)?\.(?:php|ya?ml|json)|"
            r"(?:backup|dump|database|db)\.(?:zip|sql|gz|tar)(?:$|/))",
            re.IGNORECASE,
        ),
        "Webshell": re.compile(
            r"(?:^|/)(?:c99|r57|wso|alfa|b374k|shell|cmd|mini)\w*\.php(?:$|/)",
            re.IGNORECASE,
        ),
        "CMS-Aufrufe": re.compile(
            r"(?:^|/)(?:wp-(?:admin|login(?:\.php)?|content|includes)|wordpress|xmlrpc\.php|"
            r"joomla|administrator/index\.php|drupal|sites/default|typo3|magento|"
            r"prestashop)(?:/|$)",
            re.IGNORECASE,
        ),
        "Admin-Zugriffe": re.compile(
            r"(?:^|/)(?:admin|administrator|login|signin|manage|manager|console|"
            r"dashboard|phpmyadmin|pma)(?:/|\.php(?:$|/)|$)",
            re.IGNORECASE,
        ),
        "API-Zugriffe": re.compile(
            r"(?:^|/)(?:api(?:/|$)|graphql(?:/|$)|swagger(?:/|$)|openapi(?:\.|/|$)|"
            r"v\d+(?:/|$))",
            re.IGNORECASE,
        ),
        "Informationslecks": re.compile(
            r"(?:^|/)(?:\.git/config|\.env(?:$|[./])|phpinfo(?:\.php)?|"
            r"server-status|server-info|actuator(?:/|$)|debug(?:/|$)|info\.php|"
            r"\.well-known/security\.txt|\.DS_Store)(?:$|/|\?)",
            re.IGNORECASE,
        ),
        "Schwachstellensuche": re.compile(
            r"(?:^|/)(?:vendor/phpunit|cgi-bin(?:/|$)|\.aws(?:/|$)|solr(?:/|$)|"
            r"jenkins(?:/|$)|HNAP1|boaform|autodiscover(?:/|$)|\.vscode(?:/|$)|"
            r"\.idea(?:/|$)|\.docker(?:/|$)|actuator/(?:env|heapdump))",
            re.IGNORECASE,
        ),
    }
    SCANNER_USER_AGENTS = re.compile(
        r"(?:nmap|masscan|zgrab|sqlmap|nikto|nuclei|gobuster|dirbuster|ffuf|"
        r"feroxbuster|whatweb|wpscan|nessus|acunetix|openvas|burp|qualys)",
        re.IGNORECASE,
    )
    COMMON_WEB_PORTS = {"80", "443", "8080", "8443"}

    def __init__(self, config: EnvConfig, database: Database) -> None:
        self.config = config
        self.database = database
        self.geolocator = GeoLocator(config)
        self._validated_bursts: set[int] = set()
        self.ignored_routes = self._parse_ignored_routes(config.ignore_request_routes)
        self.readers = {"traefik": self._create_traefik_reader}

    def close(self) -> None:
        """Release GeoLite database readers."""
        self.geolocator.close()

    def import_logs(
        self,
        on_file_start: Callable[[str], None] | None = None,
        on_record_imported: Callable[[], None] | None = None,
    ) -> int:
        """Process each ``type:path`` entry in ``LOG_FILES`` in order."""
        total = 0
        for entry in self.config.log_files:
            reader_type, separator, path = entry.partition(":")
            reader_type = reader_type.strip().lower()
            path = path.strip()
            if not separator or not path:
                raise ValueError(f"Invalid LOG_FILES entry {entry!r}; expected type:path")
            try:
                reader_factory = self.readers[reader_type]
            except KeyError as exc:
                raise ValueError(f"Unsupported log reader {reader_type!r} in {entry!r}") from exc

            if on_file_start is not None:
                on_file_start(path)

            def import_and_report(record: dict[str, Any]) -> bool:
                imported = self.import_request(record)
                if imported and on_record_imported is not None:
                    on_record_imported()
                return imported

            reader = reader_factory(path)
            count = reader.read(import_and_report)
            total += count
            logger.info("Imported %d request(s) from %s", count, path)
            if reader.skipped_count:
                logger.info("Skipped %d request(s) by import filters", reader.skipped_count)
        return total

    def _create_traefik_reader(self, path: str) -> TraefikReader:
        return TraefikReader(path, self.config.input_save_margin_characters)

    def import_request(self, record: dict[str, Any]) -> bool:
        """Persist an eligible Traefik record; return false when filtered out."""
        if self._is_ignored_request(record):
            return False
        actor_ip = record.get("ClientHost")
        if not actor_ip:
            client_addr = record.get("ClientAddr", "")
            actor_ip = client_addr.rsplit(":", 1)[0] if client_addr else None
        if not actor_ip:
            raise ValueError("Traefik request has no ClientHost or ClientAddr")
        actor_ip = str(actor_ip).strip()
        if not self._is_public_ip(actor_ip):
            return False

        request_host = record.get("RequestHost") or None
        timestamp = self._parse_timestamp(record.get("StartUTC") or record.get("time"))
        timestamp_text = timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
        method = str(record.get("RequestMethod") or "").upper()
        categories = self._categories_for_record(record)
        request_kind = self._request_kind(method)

        # Keep each record's related rows atomic: the reader only consumes its
        # line after this transaction commits successfully.
        with self.database.connection:
            connection = self.database.connection
            actor = connection.execute(
                "SELECT actor_id, provider, asn, city, country FROM actor WHERE ip = ?",
                (str(actor_ip),),
            ).fetchone()
            if actor is None:
                geo = self.geolocator.lookup(str(actor_ip))
                connection.execute(
                    """INSERT INTO actor (ip, first_time, last_time, provider, asn, city, country)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(actor_ip), timestamp_text, timestamp_text,
                        geo["provider"], geo["asn"], geo["city"], geo["country"],
                    ),
                )
                actor_id = connection.execute(
                    "SELECT actor_id FROM actor WHERE ip = ?", (str(actor_ip),)
                ).fetchone()[0]
            else:
                actor_id = actor["actor_id"]
                geo = self.geolocator.lookup(str(actor_ip)) if any(
                    actor[key] is None for key in ("provider", "asn", "city", "country")
                ) else {}
                connection.execute(
                    """UPDATE actor SET
                           first_time = min(first_time, ?),
                           last_time = max(last_time, ?),
                           provider = coalesce(provider, ?),
                           asn = coalesce(asn, ?),
                           city = coalesce(city, ?),
                           country = coalesce(country, ?)
                       WHERE actor_id = ?""",
                    (
                        timestamp_text, timestamp_text,
                        geo.get("provider"), geo.get("asn"), geo.get("city"), geo.get("country"),
                        actor_id,
                    ),
                )

            host_id = None
            if request_host:
                connection.execute("INSERT OR IGNORE INTO host (name) VALUES (?)", (request_host,))
                host_id = connection.execute(
                    "SELECT host_id FROM host WHERE name = ?", (request_host,)
                ).fetchone()[0]

            category_ids = [self._get_category_id(category) for category in categories]
            cursor = connection.execute(
                """INSERT INTO request (
                       actor_id, host_id, downstream_content_size, downstream_status,
                       duration, request_host, request_method, request_path,
                       request_scheme, start_utc, user_agent
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    actor_id,
                    host_id,
                    self._optional_int(record.get("DownstreamContentSize")),
                    self._optional_int(record.get("DownstreamStatus")),
                    self._optional_int(record.get("Duration")),
                    request_host,
                    method or None,
                    record.get("RequestPath"),
                    record.get("RequestScheme"),
                    timestamp_text,
                    record.get("request_User-Agent"),
                ),
            )
            request_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO request_category (request_id, category_id) VALUES (?, ?)",
                [(request_id, category_id) for category_id in category_ids],
            )
            self._update_burst(actor_id, host_id, timestamp, request_id, request_kind)
        return True

    @staticmethod
    def _is_public_ip(value: str) -> bool:
        """Only import globally routable IP addresses."""
        try:
            return ipaddress.ip_address(value).is_global
        except ValueError:
            return False

    @staticmethod
    def _parse_ignored_routes(routes: list[str]) -> list[tuple[str, str]]:
        parsed = []
        for route in routes:
            host, separator, path = route.partition("/")
            if not separator or not host:
                raise ValueError(
                    "IGNORE_REQUEST_ROUTES entries must use 'hostname/path-prefix' format"
                )
            parsed.append((host.lower().rstrip("."), "/" + path.strip("/")))
        return parsed

    def _is_ignored_request(self, record: dict[str, Any]) -> bool:
        host = str(record.get("RequestHost") or "").lower().rstrip(".")
        path = urlsplit(str(record.get("RequestPath") or "")).path or "/"
        for ignored_host, ignored_prefix in self.ignored_routes:
            if host != ignored_host:
                continue
            prefix = ignored_prefix.rstrip("/") or "/"
            if prefix == "/" or path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    def _get_category_id(self, category: str) -> int:
        connection = self.database.connection
        connection.execute("INSERT OR IGNORE INTO category (category_name) VALUES (?)", (category,))
        return connection.execute(
            "SELECT category_id FROM category WHERE category_name = ?", (category,)
        ).fetchone()[0]

    def _update_burst(
        self,
        actor_id: int,
        host_id: int | None,
        timestamp: datetime,
        request_id: int,
        request_kind: str,
    ) -> None:
        connection = self.database.connection
        max_gap = self.config.burst_max_gap_seconds
        min_requests = self.config.burst_min_requests
        window_seconds = self.config.burst_window_seconds
        if max_gap < 0:
            raise ValueError("BURST_MAX_GAP_SECONDS must not be negative")
        if min_requests < 1:
            raise ValueError("BURST_MIN_REQUESTS must be at least 1")
        if window_seconds < 1:
            raise ValueError("BURST_WINDOW_SECONDS must be greater than zero")

        previous = connection.execute(
            """SELECT burst_id, start_time, end_time, read_count, write_count, other_count
               FROM burst WHERE actor_id = ? AND host_id IS ?
               ORDER BY end_time DESC LIMIT 1""",
            (actor_id, host_id),
        ).fetchone()
        if previous is not None:
            previous_end = self._parse_timestamp(previous["end_time"])
            gap = (timestamp - previous_end).total_seconds()
        else:
            gap = max_gap + 1

        if previous is not None and 0 <= gap <= max_gap:
            burst_id = previous["burst_id"]
            counts = {
                "read_count": previous["read_count"],
                "write_count": previous["write_count"],
                "other_count": previous["other_count"],
            }
            # Bursts created before the minimum threshold was introduced may
            # still be present. Do not extend one until it qualifies.
            needs_validation = burst_id not in self._validated_bursts
            if sum(counts.values()) < min_requests or (
                needs_validation and not self._burst_has_qualifying_window(
                    actor_id, host_id, previous["start_time"], previous["end_time"],
                    min_requests, window_seconds, max_gap,
                )
            ):
                connection.execute("DELETE FROM burst WHERE burst_id = ?", (burst_id,))
                self._validated_bursts.discard(burst_id)
                previous = None
            else:
                self._validated_bursts.add(burst_id)
                count_column = {
                    "read": "read_count", "write": "write_count", "other": "other_count"
                }[request_kind]
                counts[count_column] += 1
                start_time = previous["start_time"]
                elapsed = max(0.0, (timestamp - self._parse_timestamp(start_time)).total_seconds())
                total_count = sum(counts.values())
                average = total_count / max(elapsed, 1.0)
                connection.execute(
                    """UPDATE burst SET end_time = ?, read_count = ?, write_count = ?,
                       other_count = ?, avg_count = ? WHERE burst_id = ?""",
                    (timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                     counts["read_count"], counts["write_count"], counts["other_count"],
                     average, burst_id),
                )
                self._increment_burst_categories(burst_id, request_id)
                return

        # No qualified active burst: examine the latest request sequence in
        # the configured window. A gap larger than max_gap starts a new sequence.
        window_start = timestamp - timedelta(seconds=window_seconds)
        rows = connection.execute(
            """SELECT request_id, start_utc, request_method FROM request
               WHERE actor_id = ? AND host_id IS ? AND start_utc >= ? AND start_utc <= ?
               ORDER BY start_utc, request_id""",
            (
                actor_id,
                host_id,
                window_start.isoformat(timespec="microseconds").replace("+00:00", "Z"),
                timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            ),
        ).fetchall()
        sequence = []
        for row in rows:
            if sequence:
                gap = (self._parse_timestamp(row["start_utc"])
                       - self._parse_timestamp(sequence[-1]["start_utc"])).total_seconds()
                if gap < 0 or gap > max_gap:
                    sequence = []
            sequence.append(row)

        if len(sequence) < min_requests or sequence[-1]["request_id"] != request_id:
            return

        start_time = sequence[0]["start_utc"]
        end_time = sequence[-1]["start_utc"]
        counts = {"read_count": 0, "write_count": 0, "other_count": 0}
        for row in sequence:
            counts[self._request_kind(str(row["request_method"] or "").upper()) + "_count"] += 1
        total_count = sum(counts.values())
        elapsed = max(
            0.0,
            (self._parse_timestamp(end_time) - self._parse_timestamp(start_time)).total_seconds(),
        )
        cursor = connection.execute(
            """INSERT INTO burst (
                   actor_id, host_id, start_time, end_time, avg_count,
                   read_count, write_count, other_count
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                actor_id, host_id, start_time, end_time, total_count / max(elapsed, 1.0),
                counts["read_count"], counts["write_count"], counts["other_count"],
            ),
        )
        burst_id = cursor.lastrowid
        self._validated_bursts.add(burst_id)
        category_counts = connection.execute(
            """SELECT rc.category_id, count(*) AS request_count
               FROM request_category AS rc
               JOIN request AS r ON r.request_id = rc.request_id
               WHERE r.actor_id = ? AND r.host_id IS ?
                 AND r.start_utc >= ? AND r.start_utc <= ?
               GROUP BY rc.category_id""",
            (actor_id, host_id, start_time, end_time),
        ).fetchall()
        connection.executemany(
            """INSERT INTO burst_category (burst_id, category_id, request_count)
               VALUES (?, ?, ?)""",
            [(burst_id, row["category_id"], row["request_count"]) for row in category_counts],
        )

    def _burst_has_qualifying_window(
        self,
        actor_id: int,
        host_id: int | None,
        start_time: str,
        end_time: str,
        min_requests: int,
        window_seconds: int,
        max_gap: int,
    ) -> bool:
        window_end = min(
            self._parse_timestamp(end_time),
            self._parse_timestamp(start_time) + timedelta(seconds=window_seconds),
        )
        rows = self.database.connection.execute(
            """SELECT start_utc FROM request
               WHERE actor_id = ? AND host_id IS ? AND start_utc >= ? AND start_utc <= ?
               ORDER BY start_utc, request_id""",
            (
                actor_id,
                host_id,
                start_time,
                window_end.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            ),
        ).fetchall()
        sequence_length = 0
        previous_time: datetime | None = None
        for row in rows:
            current_time = self._parse_timestamp(row["start_utc"])
            if previous_time is None or (current_time - previous_time).total_seconds() > max_gap:
                sequence_length = 1
            else:
                sequence_length += 1
            if sequence_length >= min_requests:
                return True
            previous_time = current_time
        return False

    def _increment_burst_categories(self, burst_id: int, request_id: int) -> None:
        connection = self.database.connection
        connection.execute(
            """INSERT INTO burst_category (burst_id, category_id, request_count)
               SELECT ?, category_id, 1 FROM request_category WHERE request_id = ?
               ON CONFLICT(burst_id, category_id) DO UPDATE
               SET request_count = request_count + 1""",
            (burst_id, request_id),
        )

    @classmethod
    def _request_kind(cls, method: str) -> str:
        if method in cls.READ_METHODS:
            return "read"
        if method in cls.WRITE_METHODS:
            return "write"
        return "other"

    @classmethod
    def _categories_for_record(cls, record: dict[str, Any]) -> list[str]:
        path = unquote(str(record.get("RequestPath") or "")).lower()
        user_agent = str(record.get("request_User-Agent") or "")
        categories = [
            name for name, pattern in cls.CATEGORY_PATTERNS.items()
            if pattern.search(path)
        ]
        if cls.SCANNER_USER_AGENTS.search(user_agent):
            categories.append("Scanner")

        port = str(record.get("RequestPort") or "")
        if port and port not in cls.COMMON_WEB_PORTS:
            categories.append("andere Dienste")

        # Keep every request visible in category summaries, including requests
        # that did not match a known probe pattern.
        return categories or ["andere"]

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if not value:
            raise ValueError("Traefik request has no timestamp")
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)
