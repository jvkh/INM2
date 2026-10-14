"""Dispatch configured logs to readers and persist parsed requests."""

from __future__ import annotations

import logging
import ipaddress
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from common.database import Database
from common.env import EnvConfig
from collector.geolocation import GeoLocator
from collector.traefik_reader import TraefikReader

logger = logging.getLogger(__name__)


class Importer:
    """Import log records, classify requests, and keep burst summaries current."""

    BURST_ASSIGNMENT_VERSION = "1"
    READ_METHODS = {"GET", "HEAD", "OPTIONS"}
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    CATEGORY_PATTERNS = {
        "sensible Dateien": re.compile(
            r"(?:^|/)(?:\.env(?:\.[^/]*)?|\.git(?:/|$)|\.svn(?:/|$)|"
            r"\.htaccess|\.htpasswd|\.ds_store|id_rsa|authorized_keys|"
            r"wp-config\.php|config(?:uration)?\.(?:php|ya?ml|json)|"
            r"(?:backup|dump|database|db)\.(?:zip|sql|gz|tar|7z|rar)(?:$|/)|"
            r"[^/]+\.(?:bak|backup|old|orig|save|swp)(?:$|/))",
            re.IGNORECASE,
        ),
        "Webshell": re.compile(
            r"(?:^|/)(?:php|c99|r57|wso|alfa|b374k|shell|cmd|mini|"
            r"uploader?|filemanager|filesman|marij|indoxploit|xleet|symlink)"
            r"\w*\.(?:php\d*|phtml|phar)(?:$|/)",
            re.IGNORECASE,
        ),
        "Datenbank-Dienste": re.compile(
            r"(?:^|/)(?:phpmyadmin|pma|adminer(?:\.php)?|phpminiadmin|"
            r"pgadmin(?:4)?|mongo-express|redis-commander)(?:/|$)",
            re.IGNORECASE,
        ),
        "Monitoring-Dienste": re.compile(
            r"(?:^|/)(?:grafana|prometheus|alertmanager|metrics|actuator/health|"
            r"healthz?|readyz?|livez?)(?:/|$)",
            re.IGNORECASE,
        ),
        "Container-Dienste": re.compile(
            r"(?:^|/)(?:docker|containers?|kubernetes|k8s|portainer|rancher)(?:/|$)",
            re.IGNORECASE,
        ),
        "CMS-Aufrufe": re.compile(
            r"(?:^|/)(?:wp-(?:admin|login(?:\.php)?|content|includes|json|cron\.php)|wordpress|xmlrpc\.php|"
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
        self._pending_burst_watermarks: dict[tuple[int, int | None], int] = {}
        self._pending_burst_latest: dict[tuple[int, int | None], str | None] = {}
        self._pending_full_burst_rebuilds: set[tuple[int, int | None]] = set()
        self._out_of_order_burst_keys: set[tuple[int, int | None]] = set()
        self.ignored_routes = self._parse_ignored_routes(config.ignore_request_routes)
        self.readers = {"traefik": self._create_traefik_reader}
        self._sync_known_hosts()
        self._migrate_burst_assignments()

    @staticmethod
    def _canonical_host_name(value: str) -> str:
        """Normalize DNS case/trailing dots and treat one leading www as optional."""
        name = value.strip().lower().rstrip(".")
        return name[4:] if name.startswith("www.") else name

    def _sync_known_hosts(self) -> None:
        """Replace the cached known-host list from the collector environment."""
        names = {
            self._canonical_host_name(item)
            for item in self.config.known_hosts
            if item.strip().strip(".")
        }
        connection = self.database.connection
        with connection:
            connection.execute("DELETE FROM known_host")
            connection.executemany(
                "INSERT INTO known_host (name) VALUES (?)",
                [(name,) for name in sorted(names)],
            )

    def close(self) -> None:
        """Release GeoLite database readers."""
        self.geolocator.close()

    def import_logs(
        self,
        on_file_start: Callable[[str], None] | None = None,
        on_record_imported: Callable[[], None] | None = None,
    ) -> int:
        """Process configured files and their rotated segments, oldest first."""
        total = 0
        logger.info("Import cycle started for %d configured source(s)", len(self.config.log_files))
        try:
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

                configured_path = Path(path).expanduser()
                rotated_paths = [
                    candidate for candidate in configured_path.parent.glob(configured_path.name + ".*")
                    if candidate.is_file()
                ] if configured_path.parent.exists() else []
                # Numeric logrotate suffixes count down from newest (.1), so
                # sort by modification time to consume old segments first.
                rotated_paths.sort(key=lambda item: (item.stat().st_mtime_ns, item.name))
                inputs = [(item, True) for item in rotated_paths]
                if configured_path.is_file():
                    inputs.append((configured_path, False))
                if not inputs:
                    raise FileNotFoundError(f"No log file or rotated segment found for {path}")

                for input_path, sealed in inputs:
                    input_name = str(input_path.absolute())
                    logger.info("Import source started: %s", input_name)
                    if on_file_start is not None:
                        on_file_start(input_name)
                    reader = reader_factory(str(input_path))
                    # Key cursors by device/inode, not filename: logrotate
                    # renames each segment when advancing .1 to .2 etc.
                    current_identity = reader.identity(input_path)
                    current_fingerprint = reader.fingerprint(input_path)
                    position_name = f"inode:{current_identity}"
                    position = self._get_log_position(position_name)
                    if position is None:
                        # Migrate cursors written by earlier versions under a
                        # path key, including a path that logrotate renamed.
                        position = self._get_log_position_for_identity(current_identity)

                    # Upgrade pre-fingerprint cursors once, preserving their
                    # offset while protecting subsequent runs against inode reuse.
                    if position is not None and not position.get("fingerprint"):
                        self._save_log_position(
                            position_name,
                            current_identity,
                            position["offset"],
                            current_fingerprint,
                        )
                        position["fingerprint"] = current_fingerprint

                    def save_reset_position(file_identity: str, fingerprint: str | None) -> None:
                        self._save_log_position(
                            f"inode:{file_identity}", file_identity, 0, fingerprint
                        )

                    def import_and_report(
                        record: dict[str, Any],
                        next_offset: int,
                        file_identity: str,
                        fingerprint: str | None,
                    ) -> bool:
                        imported = self.import_request(
                            record,
                            defer_burst_rebuild=True,
                            log_position=(
                                f"inode:{file_identity}",
                                file_identity,
                                next_offset,
                                fingerprint,
                            ),
                        )
                        if imported and on_record_imported is not None:
                            on_record_imported()
                        return imported

                    try:
                        count = reader.read(
                            import_and_report,
                            start_offset=position["offset"] if position else 0,
                            file_identity=position["identity"] if position else None,
                            file_fingerprint=position.get("fingerprint") if position else None,
                            on_position_reset=save_reset_position,
                            sealed=sealed,
                        )
                    except Exception:
                        logger.exception("Import source failed: %s", input_name)
                        raise
                    total += count
                    logger.info("Imported %d request(s) from %s", count, input_name)
                    if reader.skipped_count:
                        logger.info("Skipped %d request(s) by import filters", reader.skipped_count)
        finally:
            # Assign imported rows once, preserving the prior import's open tail.
            self._rebuild_pending_bursts()
        logger.info("Import cycle completed: %d request(s) imported", total)
        return total

    def _create_traefik_reader(self, path: str) -> TraefikReader:
        return TraefikReader(path, self.config.input_save_margin_characters)

    def _get_log_position(self, path: str) -> dict[str, Any] | None:
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = 'collector_log_position' AND name = ?",
            (path,),
        )
        if not rows or not rows[0]["value"]:
            return None
        try:
            value = json.loads(rows[0]["value"])
            if isinstance(value, dict) and isinstance(value.get("identity"), str) and isinstance(value.get("offset"), int):
                return value
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid saved log position for %s", path)
        return None

    def _get_log_position_for_identity(self, identity: str) -> dict[str, Any] | None:
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = 'collector_log_position'"
        )
        for row in rows:
            try:
                value = json.loads(row["value"])
                if isinstance(value, dict) and value.get("identity") == identity and isinstance(value.get("offset"), int):
                    return value
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _write_log_position(
        connection: Any,
        path: str,
        file_identity: str,
        offset: int,
        fingerprint: str | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO settings (group_name, name, value)
               VALUES ('collector_log_position', ?, ?)
               ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value""",
            (
                path,
                json.dumps({
                    "identity": file_identity,
                    "offset": offset,
                    "fingerprint": fingerprint,
                }),
            ),
        )

    def _save_log_position(
        self, path: str, file_identity: str, offset: int, fingerprint: str | None = None
    ) -> None:
        with self.database.connection:
            self._write_log_position(
                self.database.connection, path, file_identity, offset, fingerprint
            )

    def import_request(
        self,
        record: dict[str, Any],
        *,
        defer_burst_rebuild: bool = False,
        log_position: tuple[str, str, int, str | None] | None = None,
    ) -> bool:
        """Persist an eligible Traefik record; return false when filtered out."""
        if self._is_ignored_request(record):
            if log_position is not None:
                self._save_log_position(*log_position)
            return False
        actor_ip = record.get("ClientHost")
        if not actor_ip:
            client_addr = record.get("ClientAddr", "")
            actor_ip = client_addr.rsplit(":", 1)[0] if client_addr else None
        if not actor_ip:
            raise ValueError("Traefik request has no ClientHost or ClientAddr")
        actor_ip = str(actor_ip).strip()
        if not self._is_public_ip(actor_ip):
            if log_position is not None:
                self._save_log_position(*log_position)
            return False

        request_host = record.get("RequestHost") or None
        timestamp = self._parse_timestamp(record.get("StartUTC") or record.get("time"))
        timestamp_text = timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
        method = str(record.get("RequestMethod") or "").upper()
        categories = self._categories_for_record(record)

        # Keep each record's related rows atomic: the reader only consumes its
        # line after this transaction commits successfully.
        key: tuple[int, int | None]
        latest_before: str | None
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

            latest = connection.execute(
                """SELECT start_utc FROM request
                   WHERE actor_id = ? AND host_id IS ?
                   ORDER BY start_utc DESC, request_id DESC LIMIT 1""",
                (actor_id, host_id),
            ).fetchone()
            latest_before = latest["start_utc"] if latest else None

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
            key = (actor_id, host_id)
            connection.executemany(
                "INSERT INTO request_category (request_id, category_id) VALUES (?, ?)",
                [(request_id, category_id) for category_id in category_ids],
            )
            if log_position is not None:
                self._write_log_position(connection, *log_position)
        self._queue_burst_request(key, request_id, timestamp_text, latest_before)
        if not defer_burst_rebuild:
            self._rebuild_pending_bursts()
        return True

    def _queue_burst_request(
        self,
        key: tuple[int, int | None],
        request_id: int,
        timestamp: str,
        latest_before: str | None,
    ) -> None:
        if key not in self._pending_burst_watermarks:
            self._pending_burst_watermarks[key] = request_id - 1
            self._pending_burst_latest[key] = latest_before
        latest = self._pending_burst_latest.get(key)
        if latest is not None and timestamp < latest:
            self._out_of_order_burst_keys.add(key)
        if latest is None or timestamp > latest:
            self._pending_burst_latest[key] = timestamp

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
            normalized_host = urlsplit(f"//{host.strip().lower()}").hostname or host
            parsed.append((normalized_host.lower().rstrip("."), "/" + path.strip("/")))
        return parsed

    def _is_ignored_request(self, record: dict[str, Any]) -> bool:
        raw_host = str(record.get("RequestHost") or "").strip().lower()
        host = (urlsplit(f"//{raw_host}").hostname or raw_host).rstrip(".")
        path = unquote(urlsplit(str(record.get("RequestPath") or "")).path) or "/"
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

    def _migrate_burst_assignments(self) -> None:
        """Rebuild legacy bursts once and initialize exact request membership."""
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = 'collector' AND name = 'burst_assignment_version'"
        )
        if rows and rows[0]["value"] == self.BURST_ASSIGNMENT_VERSION:
            return
        keys = self.database.query(
            """SELECT actor_id, host_id FROM request
               UNION SELECT actor_id, host_id FROM burst
               ORDER BY actor_id, host_id"""
        )
        for row in keys:
            key = (row["actor_id"], row["host_id"])
            self._pending_burst_watermarks[key] = 0
            self._pending_full_burst_rebuilds.add(key)
        self._rebuild_pending_bursts()
        self.database.execute(
            """INSERT INTO settings (group_name, name, value)
               VALUES ('collector', 'burst_assignment_version', ?)
               ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value""",
            (self.BURST_ASSIGNMENT_VERSION,),
        )

    def _rebuild_pending_bursts(self) -> None:
        if self.config.burst_max_gap_seconds < 0:
            raise ValueError("BURST_MAX_GAP_SECONDS must not be negative")
        if self.config.burst_min_requests < 1:
            raise ValueError("BURST_MIN_REQUESTS must be at least 1")
        if self.config.burst_window_seconds < 1:
            raise ValueError("BURST_WINDOW_SECONDS must be greater than zero")
        pending = sorted(self._pending_burst_watermarks, key=lambda key: (key[0], key[1] or 0))
        for key in pending:
            actor_id, host_id = key
            if key in self._pending_full_burst_rebuilds or key in self._out_of_order_burst_keys:
                self._rebuild_actor_host_bursts(actor_id, host_id)
            else:
                watermark = self._pending_burst_watermarks[key]
                rows = self.database.query(
                    """SELECT request_id, start_utc, request_method FROM request
                       WHERE actor_id = ? AND host_id IS ? AND request_id > ?
                       ORDER BY start_utc, request_id""",
                    (actor_id, host_id, watermark),
                )
                for request in rows:
                    self._assign_incremental_burst_request(actor_id, host_id, request)
            self._pending_burst_watermarks.pop(key, None)
            self._pending_burst_latest.pop(key, None)
            self._pending_full_burst_rebuilds.discard(key)
            self._out_of_order_burst_keys.discard(key)

    def _assign_incremental_burst_request(
        self, actor_id: int, host_id: int | None, request: Any
    ) -> None:
        """Assign one new request, reading only its actor/host's short tail."""
        connection = self.database.connection
        timestamp = self._parse_timestamp(request["start_utc"])
        latest_burst = connection.execute(
            """SELECT burst_id, start_time, end_time, read_count, write_count, other_count
               FROM burst WHERE actor_id = ? AND host_id IS ?
               ORDER BY end_time DESC, burst_id DESC LIMIT 1""",
            (actor_id, host_id),
        ).fetchone()
        if latest_burst is not None:
            gap = (timestamp - self._parse_timestamp(latest_burst["end_time"])).total_seconds()
            if 0 <= gap <= self.config.burst_max_gap_seconds:
                self._extend_burst(latest_burst, request)
                return

        window_start = (timestamp - timedelta(seconds=self.config.burst_window_seconds)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z")
        tail = connection.execute(
            """SELECT r.request_id, r.start_utc, r.request_method, br.burst_id
               FROM request AS r
               LEFT JOIN burst_request AS br ON br.request_id = r.request_id
               WHERE r.actor_id = ? AND r.host_id IS ?
                 AND r.start_utc >= ? AND r.start_utc <= ?
               ORDER BY r.start_utc, r.request_id""",
            (actor_id, host_id, window_start, request["start_utc"]),
        ).fetchall()
        sequence: list[Any] = []
        previous: Any | None = None
        for item in tail:
            if item["burst_id"] is not None:
                sequence = []
                previous = None
                continue
            if previous is not None and (
                self._parse_timestamp(item["start_utc"])
                - self._parse_timestamp(previous["start_utc"])
            ).total_seconds() > self.config.burst_max_gap_seconds:
                sequence = []
            sequence.append(item)
            previous = item
        if len(sequence) >= self.config.burst_min_requests:
            self._create_incremental_burst(actor_id, host_id, sequence)

    def _extend_burst(self, burst: Any, request: Any) -> None:
        connection = self.database.connection
        counts = {
            "read": burst["read_count"],
            "write": burst["write_count"],
            "other": burst["other_count"],
        }
        counts[self._request_kind(str(request["request_method"] or "").upper())] += 1
        elapsed = max(
            0.0,
            (self._parse_timestamp(request["start_utc"])
             - self._parse_timestamp(burst["start_time"])).total_seconds(),
        )
        total = sum(counts.values())
        with connection:
            connection.execute(
                """UPDATE burst SET end_time = ?, avg_count = ?, read_count = ?,
                   write_count = ?, other_count = ? WHERE burst_id = ?""",
                (request["start_utc"], total / max(elapsed, 1.0), counts["read"],
                 counts["write"], counts["other"], burst["burst_id"]),
            )
            connection.execute(
                "INSERT INTO burst_request (request_id, burst_id) VALUES (?, ?)",
                (request["request_id"], burst["burst_id"]),
            )
            connection.execute(
                """INSERT INTO burst_category (burst_id, category_id, request_count)
                   SELECT ?, category_id, 1 FROM request_category WHERE request_id = ?
                   ON CONFLICT(burst_id, category_id) DO UPDATE
                   SET request_count = request_count + 1""",
                (burst["burst_id"], request["request_id"]),
            )

    def _create_incremental_burst(
        self, actor_id: int, host_id: int | None, requests: list[Any]
    ) -> None:
        connection = self.database.connection
        start_time, end_time = requests[0]["start_utc"], requests[-1]["start_utc"]
        counts = {"read": 0, "write": 0, "other": 0}
        for request in requests:
            counts[self._request_kind(str(request["request_method"] or "").upper())] += 1
        elapsed = max(0.0, (self._parse_timestamp(end_time) - self._parse_timestamp(start_time)).total_seconds())
        with connection:
            cursor = connection.execute(
                """INSERT INTO burst (actor_id, host_id, start_time, end_time, avg_count,
                   read_count, write_count, other_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (actor_id, host_id, start_time, end_time, len(requests) / max(elapsed, 1.0),
                 counts["read"], counts["write"], counts["other"]),
            )
            burst_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO burst_request (request_id, burst_id) VALUES (?, ?)",
                [(item["request_id"], burst_id) for item in requests],
            )
            connection.execute(
                """INSERT INTO burst_category (burst_id, category_id, request_count)
                   SELECT ?, rc.category_id, COUNT(*) FROM burst_request br
                   JOIN request_category rc ON rc.request_id = br.request_id
                   WHERE br.burst_id = ? GROUP BY rc.category_id""",
                (burst_id, burst_id),
            )

    def _rebuild_actor_host_bursts(self, actor_id: int, host_id: int | None) -> None:
        """Reconstruct one actor/host's bursts from its full chronological history."""
        connection = self.database.connection
        with connection:
            requests = connection.execute(
                """SELECT request_id, start_utc, request_method FROM request
                   WHERE actor_id = ? AND host_id IS ?
                   ORDER BY start_utc, request_id""",
                (actor_id, host_id),
            ).fetchall()
            old_bursts = connection.execute(
                """SELECT burst_id, start_time, end_time FROM burst
                   WHERE actor_id = ? AND host_id IS ?
                   ORDER BY start_time, burst_id""",
                (actor_id, host_id),
            ).fetchall()
            segments = self._qualified_burst_segments(requests)
            old_ids = {row["burst_id"] for row in old_bursts}
            for burst_id in old_ids:
                connection.execute("DELETE FROM burst_request WHERE burst_id = ?", (burst_id,))
                connection.execute("DELETE FROM burst_category WHERE burst_id = ?", (burst_id,))

            kept_ids: set[int] = set()
            for segment in segments:
                start_time = segment[0]["start_utc"]
                end_time = segment[-1]["start_utc"]
                overlapping = [
                    row for row in old_bursts
                    if row["burst_id"] not in kept_ids
                    and row["end_time"] >= start_time
                    and row["start_time"] <= end_time
                ]
                matching = next((row for row in overlapping if row["start_time"] == start_time), None)
                existing = matching or (overlapping[0] if overlapping else None)
                counts = {"read": 0, "write": 0, "other": 0}
                for item in segment:
                    counts[self._request_kind(str(item["request_method"] or "").upper())] += 1
                total_count = len(segment)
                elapsed = max(
                    0.0,
                    (self._parse_timestamp(end_time) - self._parse_timestamp(start_time)).total_seconds(),
                )
                values = (
                    actor_id, host_id, start_time, end_time, total_count / max(elapsed, 1.0),
                    counts["read"], counts["write"], counts["other"],
                )
                if existing is not None:
                    burst_id = existing["burst_id"]
                    connection.execute(
                        """UPDATE burst SET start_time = ?, end_time = ?, avg_count = ?,
                           read_count = ?, write_count = ?, other_count = ? WHERE burst_id = ?""",
                        (*values[2:], burst_id),
                    )
                else:
                    cursor = connection.execute(
                        """INSERT INTO burst (actor_id, host_id, start_time, end_time, avg_count,
                           read_count, write_count, other_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        values,
                    )
                    burst_id = cursor.lastrowid
                kept_ids.add(burst_id)
                connection.executemany(
                    "INSERT INTO burst_request (request_id, burst_id) VALUES (?, ?)",
                    [(item["request_id"], burst_id) for item in segment],
                )
                categories = connection.execute(
                    """SELECT rc.category_id, COUNT(*) AS request_count
                       FROM burst_request AS br
                       JOIN request_category AS rc ON rc.request_id = br.request_id
                       WHERE br.burst_id = ? GROUP BY rc.category_id""",
                    (burst_id,),
                ).fetchall()
                connection.executemany(
                    """INSERT INTO burst_category (burst_id, category_id, request_count)
                       VALUES (?, ?, ?)""",
                    [(burst_id, row["category_id"], row["request_count"]) for row in categories],
                )

            for burst_id in old_ids - kept_ids:
                connection.execute("DELETE FROM burst WHERE burst_id = ?", (burst_id,))

    def _qualified_burst_segments(self, requests: list[Any]) -> list[list[Any]]:
        """Split requests by max gap, retaining only runs that qualify in-window."""
        segments: list[list[Any]] = []
        run: list[Any] = []
        for request in requests:
            if run:
                gap = (
                    self._parse_timestamp(request["start_utc"])
                    - self._parse_timestamp(run[-1]["start_utc"])
                ).total_seconds()
                if gap > self.config.burst_max_gap_seconds:
                    self._append_qualified_run(run, segments)
                    run = []
            run.append(request)
        if run:
            self._append_qualified_run(run, segments)
        return segments

    def _append_qualified_run(self, run: list[Any], segments: list[list[Any]]) -> None:
        first_candidate = 0
        for end_index, request in enumerate(run):
            end_time = self._parse_timestamp(request["start_utc"])
            while first_candidate <= end_index and (
                end_time - self._parse_timestamp(run[first_candidate]["start_utc"])
            ).total_seconds() > self.config.burst_window_seconds:
                first_candidate += 1
            if end_index - first_candidate + 1 >= self.config.burst_min_requests:
                segments.append(run[first_candidate:])
                return

    @classmethod
    def _request_kind(cls, method: str) -> str:
        if method in cls.READ_METHODS:
            return "read"
        if method in cls.WRITE_METHODS:
            return "write"
        return "other"

    @classmethod
    def _categories_for_record(cls, record: dict[str, Any]) -> list[str]:
        # Match only the URL path; query strings should not hide a known target
        # (for example, ``/php.php?cmd=id``).
        path = unquote(urlsplit(str(record.get("RequestPath") or "")).path).lower()
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
        return categories or ["Andere Dienste"]

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
