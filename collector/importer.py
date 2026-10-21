"""Dispatch configured logs to readers and persist parsed requests."""

from __future__ import annotations

import logging
import ipaddress
import json
import hashlib
import os
import re
import fcntl
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from glob import escape as escape_glob
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from common.database import Database
from common.path_scan import PATH_SCAN_CATEGORIES
from common.env import EnvConfig
from collector.geolocation import GeoLocator
from collector.traefik_reader import TraefikReader

logger = logging.getLogger(__name__)


class Importer:
    """Import log records, classify requests, and keep burst summaries current."""

    BURST_ASSIGNMENT_VERSION = "1"
    PATH_SCAN_WINDOW_SECONDS = 600
    PATH_SCAN_MIN_DISTINCT_PATHS = 8
    PATH_SCAN_CATEGORIES = set(PATH_SCAN_CATEGORIES)
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
        self.incident_merge_overlap_ratio = config.incident_merge_overlap_percent / 100
        self.low_slow_scan_window_seconds = config.low_slow_scan_window_seconds
        self.low_slow_scan_min_paths = config.low_slow_scan_min_paths
        self.low_slow_scan_min_hosts = config.low_slow_scan_min_hosts
        self.low_slow_scan_min_span_seconds = config.low_slow_scan_min_span_seconds
        self.unknown_host_404_window_seconds = config.unknown_host_404_window_days * 86400
        self.unknown_host_404_min_requests = config.unknown_host_404_min_requests
        self.unknown_host_404_min_hosts = config.unknown_host_404_min_hosts
        if self.low_slow_scan_window_seconds < 1:
            raise ValueError("LOW_SLOW_SCAN_WINDOW_SECONDS must be greater than zero")
        if self.low_slow_scan_min_paths < 1 or self.low_slow_scan_min_hosts < 1:
            raise ValueError("LOW_SLOW_SCAN_MIN_PATHS and LOW_SLOW_SCAN_MIN_HOSTS must be at least 1")
        if self.low_slow_scan_min_span_seconds < 0:
            raise ValueError("LOW_SLOW_SCAN_MIN_SPAN_SECONDS must not be negative")
        if self.unknown_host_404_window_seconds < 1:
            raise ValueError("UNKNOWN_HOST_404_WINDOW_DAYS must be greater than zero")
        if self.unknown_host_404_min_requests < 1 or self.unknown_host_404_min_hosts < 1:
            raise ValueError("UNKNOWN_HOST_404_MIN_REQUESTS and UNKNOWN_HOST_404_MIN_HOSTS must be at least 1")
        self.geolocator = GeoLocator(config)
        self._pending_burst_watermarks: dict[tuple[int, int | None], int] = {}
        self._pending_burst_latest: dict[tuple[int, int | None], str | None] = {}
        self._pending_full_burst_rebuilds: set[tuple[int, int | None]] = set()
        self._out_of_order_burst_keys: set[tuple[int, int | None]] = set()
        self._pending_path_scan_checks: dict[tuple[int, int | None], dict[int, datetime]] = {}
        self._pending_behavior_checks: dict[tuple[int, int | None], datetime] = {}
        self._pending_low_slow_checks: dict[int, datetime] = {}
        self._pending_incident_merges: set[int] = set()
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
            cowrie_count = self.import_cowrie_log()
            total += cowrie_count
            if on_record_imported is not None:
                for _ in range(cowrie_count):
                    on_record_imported()
            honeypot_count = self.import_honeypot_log()
            total += honeypot_count
            if on_record_imported is not None:
                for _ in range(honeypot_count):
                    on_record_imported()
            for entry in self.config.log_files:
                if ":" in entry:
                    # Backward compatibility for existing configurations.
                    reader_type, _, path = entry.partition(":")
                    reader_type = reader_type.strip().lower()
                    path = path.strip()
                else:
                    # New configurations specify filenames relative to the
                    # read-only input-log directory mounted by Compose.
                    reader_type = "traefik"
                    filename = Path(entry)
                    if filename.name != entry or entry in {".", ".."} or ":" in entry:
                        raise ValueError(
                            f"Invalid LOG_FILES entry {entry!r}; expected a filename"
                        )
                    path = str(Path("/input-logs") / filename)
                if not path:
                    raise ValueError(f"Invalid LOG_FILES entry {entry!r}; path is empty")
                try:
                    reader_factory = self.readers[reader_type]
                except KeyError as exc:
                    raise ValueError(f"Unsupported log reader {reader_type!r} in {entry!r}") from exc

                configured_path = Path(path).expanduser()
                rotated_paths = [
                    candidate for candidate in configured_path.parent.glob(
                        escape_glob(configured_path.name) + ".*"
                    )
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

                    def save_skipped_position(
                        next_offset: int, file_identity: str, fingerprint: str | None
                    ) -> None:
                        self._save_log_position(
                            f"inode:{file_identity}", file_identity, next_offset, fingerprint
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
                            on_invalid_line=save_skipped_position,
                            sealed=sealed,
                        )
                    except Exception:
                        logger.exception("Import source failed: %s", input_name)
                        raise
                    total += count
                    logger.info("Imported %d request(s) from %s", count, input_name)
                    if reader.skipped_count:
                        logger.info("Skipped %d request(s) (malformed, filtered, or duplicate)", reader.skipped_count)
        finally:
            # Assign imported rows once, preserving the prior import's open tail.
            self._rebuild_pending_bursts()
            self._detect_pending_path_scans()
            self._backfill_behavior_incidents_once()
            self._merge_pending_incidents()
        logger.info("Import cycle completed: %d request(s) imported", total)
        return total

    def import_cowrie_log(self) -> int:
        """Incrementally import Cowrie JSON events, including submitted passwords."""
        enabled = os.environ.get("COWRIE_ENABLED", "false").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            logger.debug("Cowrie import is disabled (COWRIE_ENABLED=%r)", enabled)
            return 0
        log_path = Path(os.environ.get("COWRIE_LOG_PATH", "").strip() or "/cowrie-logs/cowrie.json")
        if not log_path.is_file():
            logger.warning(
                "Cowrie import is enabled, but log file %s is not accessible; check the collector bind mount",
                log_path,
            )
            return 0
        stat = log_path.stat()
        identity = f"{stat.st_dev}:{stat.st_ino}"
        position_name = "cowrie:" + str(log_path)
        saved = self._get_log_position(position_name)
        offset = saved["offset"] if saved and saved.get("identity") == identity else 0
        if offset > stat.st_size:
            logger.warning(
                "Resetting Cowrie log position for %s from byte %d to 0: file size is %d",
                log_path, offset, stat.st_size,
            )
            offset = 0
        imported = 0
        geo_enabled = self.geolocator.enabled
        stored_fields = {
            "eventid", "event_type", "timestamp", "time", "src_ip", "session", "username",
            "password", "input", "message", "sensor",
        }
        with log_path.open("rb") as stream:
            stream.seek(offset)
            contents = stream.read()
            complete = contents.rfind(b"\n") + 1
            if not complete:
                return 0
            lines = contents[:complete].splitlines()
            next_offset = offset + complete
            with self.database.connection:
                for line_number, line in enumerate(lines, start=1):
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        logger.warning("Skipping malformed Cowrie event line %d", line_number)
                        continue
                    if not isinstance(event, dict):
                        continue
                    event_type = str(event.get("eventid") or event.get("event_type") or "unknown")
                    source_ip = event.get("src_ip")
                    geo = self.geolocator.lookup(str(source_ip)) if source_ip and geo_enabled else {}
                    cursor = self.database.connection.execute(
                        """INSERT OR IGNORE INTO cowrie_event (
                               event_id, time, src_ip, session, event_type, username,
                               password, input, message, sensor, provider, asn, country, city, extra_json
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            hashlib.sha256(line).hexdigest(),
                            str(event.get("timestamp") or event.get("time") or ""),
                            str(source_ip) if source_ip else None,
                            str(event.get("session")) if event.get("session") else None,
                            event_type,
                            str(event.get("username")) if event.get("username") is not None else None,
                            str(event.get("password")) if event.get("password") is not None else None,
                            str(event.get("input")) if event.get("input") is not None else None,
                            str(event.get("message")) if event.get("message") is not None else None,
                            str(event.get("sensor")) if event.get("sensor") is not None else None,
                            geo.get("provider"), geo.get("asn"), geo.get("country"), geo.get("city"),
                            json.dumps({key: value for key, value in event.items() if key not in stored_fields}, ensure_ascii=False) or None,
                        ),
                    )
                    imported += cursor.rowcount
                self._write_log_position(
                    self.database.connection, position_name, identity, next_offset
                )
        if imported:
            logger.info("Imported %d Cowrie event(s) from %s", imported, log_path)
        # Recover extra attributes for events imported by earlier versions of
        # the collector while the corresponding JSON lines are still present.
        pending_ids = {
            row["event_id"]
            for row in self.database.query(
                "SELECT event_id FROM cowrie_event WHERE extra_json IS NULL"
            )
        }
        if pending_ids:
            with log_path.open("rb") as stream, self.database.connection:
                for line in stream:
                    event_id = hashlib.sha256(line.rstrip(b"\r\n")).hexdigest()
                    if event_id not in pending_ids:
                        continue
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    extras = {key: value for key, value in event.items() if key not in stored_fields} if isinstance(event, dict) else {}
                    self.database.connection.execute(
                        "UPDATE cowrie_event SET extra_json=? WHERE event_id=?",
                        (json.dumps(extras, ensure_ascii=False), event_id),
                    )
                    pending_ids.discard(event_id)
            if pending_ids:
                logger.info("No original Cowrie JSON line found for %d older event(s); preserving them without extra fields", len(pending_ids))
                with self.database.connection:
                    self.database.connection.execute(
                        "UPDATE cowrie_event SET extra_json='{}' WHERE extra_json IS NULL"
                    )
        if geo_enabled:
            pending_ips = self.database.query(
                """SELECT DISTINCT src_ip FROM cowrie_event WHERE src_ip IS NOT NULL
                   AND (provider IS NULL OR asn IS NULL OR country IS NULL OR city IS NULL)"""
            )
            if pending_ips:
                with self.database.connection:
                    for row in pending_ips:
                        geo = self.geolocator.lookup(row["src_ip"])
                        self.database.connection.execute(
                            """UPDATE cowrie_event SET provider=COALESCE(provider, ?),
                                   asn=COALESCE(asn, ?), country=COALESCE(country, ?), city=COALESCE(city, ?)
                               WHERE src_ip=?""",
                            (geo.get("provider"), geo.get("asn"), geo.get("country"), geo.get("city"), row["src_ip"]),
                        )
        return imported

    def import_honeypot_log(self) -> int:
        """Import and acknowledge the honeypot's shared JSONL queue."""
        log_path = Path(os.environ.get("HONEYPOT_LOG_PATH", "/logs/honeypot.jsonl"))
        if not log_path.is_file():
            return 0
        imported = 0
        with log_path.open("r+b") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            contents = stream.read()
            complete = contents.rfind(b"\n") + 1
            if not complete:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                return 0
            lines = contents[:complete].splitlines()
            with self.database.connection:
                for line_number, line in enumerate(lines, start=1):
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        logger.warning("Skipping malformed honeypot event line %d", line_number)
                        continue
                    if not isinstance(event, dict):
                        logger.warning("Skipping non-object honeypot event line %d", line_number)
                        continue
                    event_id = event.get("event_id")
                    if not isinstance(event_id, str) or not re.fullmatch(r"[a-f0-9]{32}", event_id):
                        logger.warning("Skipping honeypot event with invalid identifier on line %d", line_number)
                        continue
                    client_ip = event.get("client_ip")
                    geo = self.geolocator.lookup(client_ip) if isinstance(client_ip, str) and client_ip else {}
                    cursor = self.database.connection.execute(
                        """INSERT OR IGNORE INTO honeypot_event (
                               event_id, time, client_ip, provider, asn, country, city,
                               host, scheme, session_id, session_phase, method, path, user_agent,
                               content_type, body_bytes, body_clipped, body_sha256, rule,
                               status, duration, body_text, body_base64, body_file
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            event_id, event.get("time", ""), client_ip,
                            geo.get("provider"), geo.get("asn"), geo.get("country"), geo.get("city"),
                            event.get("host"), event.get("scheme"), event.get("session_id"), event.get("session_phase"),
                            event.get("method", ""), event.get("path", ""),
                            event.get("user_agent"), event.get("content_type"),
                            int(event.get("body_bytes", 0)), int(bool(event.get("body_clipped"))),
                            event.get("body_sha256"), event.get("rule"), event.get("status"),
                            int(event.get("duration", 0)), event.get("body_text"), event.get("body_base64"),
                            event.get("body_file"),
                        ),
                    )
                    imported += cursor.rowcount
            # Only acknowledge complete records after their DB transaction
            # succeeded; keep an incomplete trailing record for the next poll.
            remaining = contents[complete:]
            stream.seek(0)
            stream.truncate()
            if remaining:
                stream.write(remaining)
            stream.flush()
            os.fsync(stream.fileno())
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        if imported:
            logger.info("Imported %d honeypot event(s) from %s", imported, log_path)
        return imported

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
        downstream_status = self._optional_int(record.get("DownstreamStatus"))
        downstream_content_size = self._optional_int(record.get("DownstreamContentSize"))
        duration = self._optional_int(record.get("Duration"))
        request_path = record.get("RequestPath")
        request_scheme = record.get("RequestScheme")
        user_agent = record.get("request_User-Agent")
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

            duplicate = connection.execute(
                """SELECT request_id FROM request
                   WHERE actor_id = ? AND host_id IS ? AND start_utc = ?
                     AND request_method IS ? AND request_path IS ? AND request_scheme IS ?
                     AND user_agent IS ? AND downstream_status IS ?
                     AND downstream_content_size IS ? AND duration IS ?
                   LIMIT 1""",
                (
                    actor_id, host_id, timestamp_text, method or None, request_path,
                    request_scheme, user_agent, downstream_status,
                    downstream_content_size, duration,
                ),
            ).fetchone()
            if duplicate is not None:
                if log_position is not None:
                    self._write_log_position(connection, *log_position)
                logger.debug(
                    "Skipping duplicate access-log record matching request %s",
                    duplicate["request_id"],
                )
                return False

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
                    downstream_content_size,
                    downstream_status,
                    duration,
                    request_host,
                    method or None,
                    request_path,
                    request_scheme,
                    timestamp_text,
                    user_agent,
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
        if self.PATH_SCAN_CATEGORIES.intersection(categories) or (downstream_status or 0) >= 400:
            self._pending_low_slow_checks[actor_id] = max(
                self._pending_low_slow_checks.get(actor_id, timestamp), timestamp
            )
        if self.PATH_SCAN_CATEGORIES.intersection(categories):
            if defer_burst_rebuild:
                key = (actor_id, host_id)
                bucket = int(timestamp.timestamp()) // self.PATH_SCAN_WINDOW_SECONDS
                checks = self._pending_path_scan_checks.setdefault(key, {})
                checks[bucket] = max(checks.get(bucket, timestamp), timestamp)
            else:
                self._detect_path_scan(actor_id, host_id, timestamp)
        if defer_burst_rebuild:
            self._pending_behavior_checks[key] = max(self._pending_behavior_checks.get(key, timestamp), timestamp)
        else:
            self._detect_behavior_incidents(actor_id, host_id, timestamp)
        if not defer_burst_rebuild:
            self._rebuild_pending_bursts()
        return True

    def _detect_pending_path_scans(self) -> None:
        """Check at most once per actor, host, and ten-minute event-time bucket."""
        pending = self._pending_path_scan_checks
        self._pending_path_scan_checks = {}
        for key, checks in pending.items():
            for event_time in sorted(checks.values()):
                self._detect_path_scan(key[0], key[1], event_time)
        behavior_checks = self._pending_behavior_checks
        self._pending_behavior_checks = {}
        for (actor_id, host_id), event_time in behavior_checks.items():
            self._detect_behavior_incidents(actor_id, host_id, event_time)
        low_slow_checks = self._pending_low_slow_checks
        self._pending_low_slow_checks = {}
        for actor_id, event_time in low_slow_checks.items():
            self._detect_low_slow_path_scan(actor_id, event_time)
            self._detect_unknown_host_404_activity(actor_id, event_time)

    def _backfill_behavior_incidents_once(self) -> None:
        """Evaluate the latest stored activity window once after upgrading."""
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = 'collector' AND name = 'incident_detection_version'"
        )
        if rows and rows[0]["value"] == "4":
            self._backfill_incident_metrics_once()
            return
        activity = self.database.query(
            """SELECT actor_id, host_id, MAX(start_utc) AS last_seen FROM request
               GROUP BY actor_id, host_id"""
        )
        for item in activity:
            try:
                event_time = datetime.fromisoformat(item["last_seen"].replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            self._detect_behavior_incidents(item["actor_id"], item["host_id"], event_time)
        low_slow_activity = self.database.query(
            f"""SELECT r.actor_id, MAX(r.start_utc) AS last_seen FROM request AS r
                LEFT JOIN request_category AS rc ON rc.request_id = r.request_id
                LEFT JOIN category AS c ON c.category_id = rc.category_id
                WHERE c.category_name IN ({','.join('?' for _ in self.PATH_SCAN_CATEGORIES)}) OR r.downstream_status >= 400
                GROUP BY r.actor_id""",
            tuple(sorted(self.PATH_SCAN_CATEGORIES)),
        )
        for item in low_slow_activity:
            try:
                event_time = datetime.fromisoformat(item["last_seen"].replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            self._detect_low_slow_path_scan(item["actor_id"], event_time)
        unknown_host_404_activity = self.database.query(
            """SELECT r.actor_id, MAX(r.start_utc) AS last_seen
               FROM request AS r
               LEFT JOIN host AS h ON h.host_id = r.host_id
               WHERE r.downstream_status = 404 AND COALESCE(h.known, 0) = 0
                 AND r.user_agent IS NOT NULL AND trim(r.user_agent) <> ''
               GROUP BY r.actor_id"""
        )
        for item in unknown_host_404_activity:
            try:
                event_time = datetime.fromisoformat(item["last_seen"].replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            self._detect_unknown_host_404_activity(item["actor_id"], event_time)
        self.database.execute(
            "INSERT INTO settings (group_name, name, value) VALUES ('collector', 'incident_detection_version', '4') "
            "ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value"
        )
        self._backfill_incident_metrics_once()

    def _detect_unknown_host_404_activity(self, actor_id: int, event_time: datetime) -> None:
        """Group repeated 404 probes to unknown hosts by actor and User-Agent."""
        window_start = event_time - timedelta(seconds=self.unknown_host_404_window_seconds)
        start_text = window_start.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        end_text = event_time.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        rows = self.database.query(
            """SELECT r.request_id, r.start_utc, r.request_path, r.user_agent,
                      r.host_id, h.name AS host_name
               FROM request AS r
               LEFT JOIN host AS h ON h.host_id = r.host_id
               WHERE r.actor_id = ? AND r.start_utc >= ? AND r.start_utc <= ?
                 AND r.downstream_status = 404 AND COALESCE(h.known, 0) = 0
                 AND r.user_agent IS NOT NULL AND trim(r.user_agent) <> ''
               ORDER BY r.user_agent COLLATE NOCASE, r.start_utc, r.request_id""",
            (actor_id, start_text, end_text),
        )
        by_user_agent: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_user_agent.setdefault(str(row["user_agent"]).strip(), []).append(row)
        for user_agent, matching in by_user_agent.items():
            hosts = {str(row["host_name"]).casefold() for row in matching if row["host_name"]}
            if len(matching) < self.unknown_host_404_min_requests or len(hosts) < self.unknown_host_404_min_hosts:
                continue
            host_names = sorted({str(row["host_name"]) for row in matching if row["host_name"]}, key=str.casefold)
            summary = {"host_count": len(hosts), "not_found_count": len(matching)}
            self._store_behavior_incident(
                "unknown_host_404_activity",
                actor_id,
                None,
                matching,
                additional_indicators=[f"Host: {name}" for name in host_names] + [f"User-Agent: {user_agent}"],
                summary=summary,
            )

    def _backfill_incident_metrics_once(self) -> None:
        """Rebuild stored detector metrics after summary definitions change."""
        version = self.database.query(
            "SELECT value FROM settings WHERE group_name = 'collector' AND name = 'incident_metrics_version'"
        )
        if version and version[0]["value"] == "2":
            return
        incidents = self.database.query(
            """SELECT incident_id, incident_type, actor_id, host_id, last_seen
               FROM incident WHERE incident_type IN ('http_error_spike', 'activity_spike')"""
        )
        for incident in incidents:
            membership = self.database.query(
                """SELECT r.start_utc, r.downstream_status FROM incident_request AS ir
                   JOIN request AS r ON r.request_id = ir.request_id
                   WHERE ir.incident_id = ? ORDER BY r.start_utc, r.request_id""",
                (incident["incident_id"],),
            )
            if incident["incident_type"] == "http_error_spike":
                try:
                    end = datetime.fromisoformat(incident["last_seen"].replace("Z", "+00:00"))
                except (AttributeError, ValueError):
                    continue
                start_text = (end - timedelta(seconds=self.PATH_SCAN_WINDOW_SECONDS)).astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
                end_text = end.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
                responses = self.database.query(
                    """SELECT downstream_status FROM request WHERE actor_id = ? AND host_id IS ?
                       AND start_utc >= ? AND start_utc <= ? AND downstream_status IS NOT NULL""",
                    (incident["actor_id"], incident["host_id"], start_text, end_text),
                )
                errors = sum(1 for row in membership if row["downstream_status"] is not None and row["downstream_status"] >= 400)
                non_errors = sum(1 for row in responses if row["downstream_status"] < 400)
                summary = {"error_count": errors, "non_error_count": non_errors}
            else:
                per_second: dict[int, int] = {}
                for row in membership:
                    try:
                        second = int(datetime.fromisoformat(row["start_utc"].replace("Z", "+00:00")).timestamp())
                    except (AttributeError, ValueError):
                        continue
                    per_second[second] = per_second.get(second, 0) + 1
                if not per_second:
                    continue
                first_second, last_second = min(per_second), max(per_second)
                rates = [per_second.get(second, 0) for second in range(first_second, last_second + 1)]
                summary = {"average_rps": round(len(membership) / len(rates), 2), "max_rps": max(rates), "min_rps": min(rates)}
            self.database.execute(
                "UPDATE incident SET summary = ?, indicator_count = ? WHERE incident_id = ?",
                (json.dumps(summary), len(summary), incident["incident_id"]),
            )
        self.database.execute(
            "INSERT INTO settings (group_name, name, value) VALUES ('collector', 'incident_metrics_version', '2') "
            "ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value"
        )

    def _detect_path_scan(
        self, actor_id: int, host_id: int | None, event_time: datetime
    ) -> None:
        """Record a path-scan incident after one source probes many sensitive paths."""
        window_start = event_time - timedelta(seconds=self.PATH_SCAN_WINDOW_SECONDS)
        start_text = window_start.isoformat(timespec="microseconds").replace("+00:00", "Z")
        end_text = event_time.isoformat(timespec="microseconds").replace("+00:00", "Z")
        placeholders = ",".join("?" for _ in self.PATH_SCAN_CATEGORIES)
        rows = self.database.query(
            f"""SELECT r.request_id, r.start_utc, r.request_path
                FROM request AS r
                WHERE r.actor_id = ? AND r.host_id IS ?
                  AND r.start_utc >= ? AND r.start_utc <= ?
                  AND EXISTS (
                      SELECT 1 FROM request_category AS rc
                      JOIN category AS c ON c.category_id = rc.category_id
                      WHERE rc.request_id = r.request_id
                        AND c.category_name IN ({placeholders})
                  )
                ORDER BY r.start_utc, r.request_id""",
            (actor_id, host_id, start_text, end_text, *sorted(self.PATH_SCAN_CATEGORIES)),
        )
        paths: dict[str, str] = {}
        for row in rows:
            path = unquote(urlsplit(str(row["request_path"] or "/")).path) or "/"
            paths.setdefault(path.casefold(), path)
        if len(paths) < self.PATH_SCAN_MIN_DISTINCT_PATHS:
            return

        matched_paths = sorted(paths.values(), key=str.casefold)[:50]
        first_seen = rows[0]["start_utc"]
        last_seen = rows[-1]["start_utc"]
        connection = self.database.connection
        with connection:
            active = connection.execute(
                """SELECT i.incident_id FROM incident AS i
                   WHERE EXISTS (SELECT 1 FROM incident_criterion AS ic
                                 WHERE ic.incident_id = i.incident_id AND ic.incident_type = 'path_scan')
                     AND i.actor_id = ? AND i.host_id IS ? AND i.state IN ('open', 'acknowledged')
                     AND i.last_seen >= ?
                   ORDER BY i.last_seen DESC, i.incident_id DESC LIMIT 1""",
                (actor_id, host_id, start_text),
            ).fetchone()
            if active is None:
                connection.execute(
                    """INSERT INTO incident (
                           incident_type, actor_id, host_id, first_seen, last_seen, request_count,
                           indicator_count, indicators
                       ) VALUES ('path_scan', ?, ?, ?, ?, ?, ?, ?)""",
                    (actor_id, host_id, first_seen, last_seen, len(rows), len(paths), json.dumps(matched_paths)),
                )
                incident_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            else:
                connection.execute(
                    """UPDATE incident SET
                           first_seen = min(first_seen, ?), last_seen = max(last_seen, ?),
                           request_count = ?, indicator_count = ?, indicators = ?, state = 'open'
                       WHERE incident_id = ?""",
                    (first_seen, last_seen, len(rows), len(paths), json.dumps(matched_paths), active["incident_id"]),
                )
                incident_id = active["incident_id"]
            connection.executemany(
                "INSERT OR IGNORE INTO incident_request (incident_id, request_id) VALUES (?, ?)",
                [(incident_id, row["request_id"]) for row in rows],
            )
            connection.execute(
                "INSERT OR IGNORE INTO incident_criterion (incident_id, incident_type) VALUES (?, 'path_scan')",
                (incident_id,),
            )
            connection.execute(
                "UPDATE incident SET request_count = (SELECT COUNT(*) FROM incident_request WHERE incident_id = ?) WHERE incident_id = ?",
                (incident_id, incident_id),
            )
            self._pending_incident_merges.add(incident_id)

    def _detect_low_slow_path_scan(self, actor_id: int, event_time: datetime) -> None:
        """Detect a slow path probe spread across multiple hosts over several hours."""
        window_start = event_time - timedelta(seconds=self.low_slow_scan_window_seconds)
        start_text = window_start.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        end_text = event_time.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        placeholders = ",".join("?" for _ in self.PATH_SCAN_CATEGORIES)
        rows = self.database.query(
            f"""SELECT r.request_id, r.start_utc, r.request_path, r.host_id, h.name AS host_name,
                       c.category_name
                FROM request AS r
                JOIN request_category AS rc ON rc.request_id = r.request_id
                JOIN category AS c ON c.category_id = rc.category_id
                LEFT JOIN host AS h ON h.host_id = r.host_id
                WHERE r.actor_id = ? AND r.start_utc >= ? AND r.start_utc <= ?
                  AND (c.category_name IN ({placeholders}) OR r.downstream_status >= 400)
                ORDER BY r.start_utc, r.request_id""",
            (actor_id, start_text, end_text, *sorted(self.PATH_SCAN_CATEGORIES)),
        )
        requests: dict[int, dict[str, Any]] = {}
        paths: dict[str, str] = {}
        hosts: set[int] = set()
        host_names: set[str] = set()
        for row in rows:
            requests.setdefault(row["request_id"], row)
            path = unquote(urlsplit(str(row["request_path"] or "/")).path) or "/"
            paths.setdefault(path.casefold(), path)
            if row["host_id"] is not None:
                hosts.add(row["host_id"])
            if row["host_name"]:
                host_names.add(row["host_name"])
        matches = list(requests.values())
        if len(paths) < self.low_slow_scan_min_paths or len(hosts) < self.low_slow_scan_min_hosts:
            return
        first_seen, last_seen = matches[0]["start_utc"], matches[-1]["start_utc"]
        span = datetime.fromisoformat(last_seen.replace("Z", "+00:00")) - datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
        if span.total_seconds() < self.low_slow_scan_min_span_seconds:
            return
        summary = {
            "distinct_path_count": len(paths),
            "host_count": len(hosts),
            "duration_seconds": int(span.total_seconds()),
        }
        self._store_behavior_incident(
            "low_slow_path_scan", actor_id, None, matches,
            additional_indicators=[f"Host: {name}" for name in sorted(host_names)],
            summary=summary,
        )

    def _detect_behavior_incidents(
        self, actor_id: int, host_id: int | None, event_time: datetime
    ) -> None:
        """Detect bounded, explainable access-log patterns for one actor and host."""
        from datetime import timezone

        window_start = event_time - timedelta(seconds=self.PATH_SCAN_WINDOW_SECONDS)
        start_text = window_start.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        end_text = event_time.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
        rows = self.database.query(
            """SELECT r.request_id, r.start_utc, r.request_path, r.request_method, r.user_agent,
                      r.downstream_status, category.category_name AS category_name
               FROM request AS r
               LEFT JOIN request_category ON request_category.request_id = r.request_id
               LEFT JOIN category ON category.category_id = request_category.category_id
               WHERE r.actor_id = ? AND r.host_id IS ? AND r.start_utc >= ? AND r.start_utc <= ?
               ORDER BY r.start_utc, r.request_id""",
            (actor_id, host_id, start_text, end_text),
        )
        requests: dict[int, dict[str, Any]] = {}
        categories: dict[int, set[str]] = {}
        for row in rows:
            requests.setdefault(row["request_id"], row)
            categories.setdefault(row["request_id"], set()).add(row["category_name"] or "")
        rows = list(requests.values())

        def normalized_path(row: dict[str, Any]) -> str:
            return unquote(urlsplit(str(row.get("request_path") or "/")).path) or "/"

        login_rows = [row for row in rows if re.search(r"(?:^|/)(?:login|signin|sign-in|auth|session)(?:/|\.|$)", normalized_path(row), re.I) and row.get("downstream_status") in (401, 403)]
        sensitive_rows = [row for row in rows if row.get("downstream_status") in (200, 206) and re.search(r"(?:^|/)(?:\.env(?:\.[^/]*)?|\.git/config|\.svn|backup[^/]*\.(?:zip|sql|gz)|wp-config\.php|id_rsa|authorized_keys|phpinfo\.php)(?:$|/)", normalized_path(row), re.I)]
        exploit_rows = [row for row in rows if row.get("downstream_status") is not None and 200 <= row["downstream_status"] < 300 and categories.get(row["request_id"], set()).intersection({"Schwachstellensuche", "Webshell"})]
        write_rows = [row for row in rows if (row.get("request_method") or "").upper() in {"POST", "PUT", "PATCH", "DELETE"} and re.search(r"(?:^|/)(?:admin|administrator|login|auth|api|graphql)(?:/|$)", normalized_path(row), re.I)]
        error_rows = [row for row in rows if row.get("downstream_status") is not None and row["downstream_status"] >= 400]
        scanner_rows = [row for row in rows if re.search(r"(?:nuclei|nikto|sqlmap|masscan|zgrab|wpscan|acunetix|nessus|openvas|gobuster|dirbuster)", row.get("user_agent") or "", re.I)]
        activity_rows = rows if len(rows) >= 50 else []
        response_rows = [row for row in rows if row.get("downstream_status") is not None]
        non_error_rows = [row for row in response_rows if row["downstream_status"] < 400]

        candidates = [
            ("failed_login", login_rows, 5),
            ("sensitive_file_access", sensitive_rows, 1),
            ("exploit_response", exploit_rows, 1),
            ("write_activity", write_rows, 5),
            ("http_error_spike", error_rows, 20),
            ("scanner_activity", scanner_rows, 5),
            ("activity_spike", activity_rows, 50),
        ]
        for incident_type, matching, threshold in candidates:
            if len(matching) < threshold:
                continue
            summary: dict[str, float | int] = {}
            if incident_type == "http_error_spike":
                summary = {
                    "error_count": len(error_rows),
                    "non_error_count": len(non_error_rows),
                }
            elif incident_type == "activity_spike":
                per_second: dict[int, int] = {}
                for row in matching:
                    request_time = datetime.fromisoformat(row["start_utc"].replace("Z", "+00:00"))
                    second = int(request_time.timestamp())
                    per_second[second] = per_second.get(second, 0) + 1
                first_second, last_second = min(per_second), max(per_second)
                rates = [per_second.get(second, 0) for second in range(first_second, last_second + 1)]
                summary = {
                    "average_rps": round(len(matching) / len(rates), 2),
                    "max_rps": max(rates),
                    "min_rps": min(rates),
                }
            self._store_behavior_incident(incident_type, actor_id, host_id, matching, summary=summary)

        if host_id is not None and len(rows) >= 3:
            dormant_cutoff = (datetime.fromisoformat(rows[0]["start_utc"].replace("Z", "+00:00")) - timedelta(days=30)).isoformat(timespec="microseconds").replace("+00:00", "Z")
            host_history = self.database.query(
                """SELECT MAX(start_utc) AS last_seen FROM request
                   WHERE host_id = ? AND start_utc < ? AND start_utc >= ?""",
                (host_id, rows[0]["start_utc"], "0001-01-01T00:00:00.000000Z"),
            )
            if host_history and host_history[0]["last_seen"] is not None and host_history[0]["last_seen"] < dormant_cutoff:
                self._store_behavior_incident("dormant_host_activity", actor_id, host_id, rows)

    def _store_behavior_incident(
        self, incident_type: str, actor_id: int, host_id: int | None,
        rows: list[dict[str, Any]], additional_indicators: list[str] | None = None,
        summary: dict[str, float | int] | None = None,
    ) -> None:
        """Create or extend one active incident and persist its request membership."""
        first_seen, last_seen = rows[0]["start_utc"], rows[-1]["start_utc"]
        indicators = [] if incident_type in {"http_error_spike", "activity_spike"} else sorted(
            {str(row.get("request_path") or "/") for row in rows}.union(additional_indicators or []),
            key=str.casefold,
        )[:50]
        indicator_count = len(summary or {}) if incident_type in {"http_error_spike", "activity_spike"} else len(indicators)
        if incident_type == "low_slow_path_scan":
            active_window = self.low_slow_scan_window_seconds
        elif incident_type == "unknown_host_404_activity":
            active_window = self.unknown_host_404_window_seconds
        else:
            active_window = self.PATH_SCAN_WINDOW_SECONDS
        start_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00")) - timedelta(seconds=active_window)
        active_since = start_dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
        connection = self.database.connection
        with connection:
            active = connection.execute(
                """SELECT i.incident_id, i.incident_type, i.indicators, i.summary FROM incident AS i
                   WHERE EXISTS (
                         SELECT 1 FROM incident_criterion AS ic
                         WHERE ic.incident_id = i.incident_id AND ic.incident_type = ?
                   ) AND i.actor_id = ? AND i.host_id IS ?
                     AND state IN ('open', 'acknowledged') AND last_seen >= ?
                   ORDER BY i.last_seen DESC, i.incident_id DESC LIMIT 1""",
                (incident_type, actor_id, host_id, active_since),
            ).fetchone()
            if active is None:
                cursor = connection.execute(
                    """INSERT INTO incident (incident_type, actor_id, host_id, first_seen, last_seen,
                                              request_count, indicator_count, indicators, summary)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (incident_type, actor_id, host_id, first_seen, last_seen, len(rows), indicator_count, json.dumps(indicators), json.dumps(summary or {})),
                )
                incident_id = cursor.lastrowid
                incident_summary = self._combine_type_summaries({}, incident_type, summary or {})
                connection.execute(
                    "INSERT INTO incident_criterion (incident_id, incident_type) VALUES (?, ?)",
                    (incident_id, incident_type),
                )
                connection.execute(
                    "UPDATE incident SET summary = ? WHERE incident_id = ?",
                    (json.dumps(incident_summary), incident_id),
                )
            else:
                incident_id = active["incident_id"]
                try:
                    previous_summary = json.loads(active["summary"] or "{}")
                except (TypeError, ValueError):
                    previous_summary = {}
                incident_summary = self._combine_type_summaries(
                    previous_summary, incident_type, summary or {}, active["incident_type"]
                )
                try:
                    prior = json.loads(active["indicators"] or "[]")
                except (TypeError, ValueError):
                    prior = []
                combined = sorted(set(prior).union(indicators), key=str.casefold)[:50]
                connection.execute(
                    """UPDATE incident SET first_seen = min(first_seen, ?), last_seen = max(last_seen, ?),
                           indicator_count = ?, indicators = ?, summary = ?, state = 'open'
                       WHERE incident_id = ?""",
                    (first_seen, last_seen, indicator_count if incident_type in {"http_error_spike", "activity_spike"} else len(combined), json.dumps(combined), json.dumps(incident_summary), incident_id),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO incident_criterion (incident_id, incident_type) VALUES (?, ?)",
                    (incident_id, incident_type),
                )
            connection.executemany(
                "INSERT OR IGNORE INTO incident_request (incident_id, request_id) VALUES (?, ?)",
                [(incident_id, row["request_id"]) for row in rows],
            )
            connection.execute(
                "UPDATE incident SET request_count = (SELECT COUNT(*) FROM incident_request WHERE incident_id = ?) WHERE incident_id = ?",
                (incident_id, incident_id),
            )
            self._pending_incident_merges.add(incident_id)

    @staticmethod
    def _combine_type_summaries(
        previous: dict[str, Any], incident_type: str, current: dict[str, Any], primary_type: str | None = None
    ) -> dict[str, Any]:
        """Retain detector-specific metrics as one incident extends or merges."""
        reserved = {"criteria", "host_count"}
        current_host_count = current.get("host_count")
        by_type = dict(previous.get("criteria", {})) if isinstance(previous.get("criteria"), dict) else {}
        if not by_type and primary_type:
            legacy = {key: value for key, value in previous.items() if key not in reserved}
            if legacy:
                by_type[primary_type] = legacy
        existing = dict(by_type.get(incident_type, {}))
        for key, value in current.items():
            prior = existing.get(key)
            if isinstance(prior, (int, float)) and isinstance(value, (int, float)):
                existing[key] = min(prior, value) if key == "min_rps" else max(prior, value)
            else:
                existing[key] = value
        by_type[incident_type] = existing
        combined: dict[str, Any] = {}
        for metrics in by_type.values():
            for key, value in metrics.items():
                prior = combined.get(key)
                if isinstance(prior, (int, float)) and isinstance(value, (int, float)):
                    combined[key] = min(prior, value) if key == "min_rps" else max(prior, value)
                else:
                    combined.setdefault(key, value)
        combined["criteria"] = by_type
        host_counts = [value for value in (previous.get("host_count"), current_host_count) if isinstance(value, (int, float))]
        if host_counts:
            combined["host_count"] = max(host_counts)
        return combined

    @staticmethod
    def _incident_overlap_ratio(first_start: str, first_end: str, second_start: str, second_end: str) -> float:
        parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
        a_start, a_end, b_start, b_end = map(parse, (first_start, first_end, second_start, second_end))
        intersection = max(0.0, (min(a_end, b_end) - max(a_start, b_start)).total_seconds())
        shorter = min((a_end - a_start).total_seconds(), (b_end - b_start).total_seconds())
        if shorter <= 0:
            return 1.0 if a_start == b_start and a_end == b_end else 0.0
        return intersection / shorter

    def _merge_pending_incidents(self) -> None:
        """Combine same-actor incidents whose overlap exceeds the configured threshold."""
        pending = self._pending_incident_merges
        self._pending_incident_merges = set()
        connection = self.database.connection
        for seed_id in pending:
            seed = connection.execute(
                "SELECT incident_id, actor_id, first_seen, last_seen FROM incident WHERE incident_id = ?",
                (seed_id,),
            ).fetchone()
            if seed is None:
                continue
            component: dict[int, Any] = {seed["incident_id"]: seed}
            queue = [seed]
            while queue:
                current = queue.pop()
                neighbors = connection.execute(
                    """SELECT incident_id, actor_id, first_seen, last_seen FROM incident
                       WHERE actor_id = ? AND first_seen <= ? AND last_seen >= ?
                       ORDER BY first_seen, incident_id""",
                    (seed["actor_id"], current["last_seen"], current["first_seen"]),
                ).fetchall()
                for candidate in neighbors:
                    if candidate["incident_id"] in component:
                        continue
                    if self._incident_overlap_ratio(
                        current["first_seen"], current["last_seen"], candidate["first_seen"], candidate["last_seen"]
                    ) > self.incident_merge_overlap_ratio:
                        component[candidate["incident_id"]] = candidate
                        queue.append(candidate)
            if len(component) < 2:
                continue
            incident_ids = sorted(component)
            keeper_id = incident_ids[0]
            placeholders = ",".join("?" for _ in incident_ids)
            records = connection.execute(
                f"SELECT * FROM incident WHERE incident_id IN ({placeholders}) ORDER BY incident_id",
                incident_ids,
            ).fetchall()
            criteria = connection.execute(
                f"SELECT DISTINCT incident_type FROM incident_criterion WHERE incident_id IN ({placeholders})",
                incident_ids,
            ).fetchall()
            criterion_types = {row["incident_type"] for row in criteria}
            criterion_types.update(row["incident_type"] for row in records)
            indicators: set[str] = set()
            summaries: dict[str, Any] = {}
            for record in records:
                try:
                    indicators.update(json.loads(record["indicators"] or "[]"))
                except (TypeError, ValueError):
                    pass
                try:
                    current_summary = json.loads(record["summary"] or "{}")
                except (TypeError, ValueError):
                    current_summary = {}
                type_summaries = current_summary.get("criteria")
                if not isinstance(type_summaries, dict):
                    type_summaries = {
                        record["incident_type"]: {
                            key: value for key, value in current_summary.items()
                            if key not in {"criteria", "host_count"}
                        }
                    }
                for criterion, metrics in type_summaries.items():
                    if isinstance(metrics, dict):
                        summaries = self._combine_type_summaries(summaries, criterion, metrics)
            states = {record["state"] for record in records}
            merged_state = "open" if "open" in states else "acknowledged" if "acknowledged" in states else "resolved"
            with connection:
                for duplicate_id in incident_ids[1:]:
                    connection.execute(
                        "INSERT OR IGNORE INTO incident_request (incident_id, request_id) SELECT ?, request_id FROM incident_request WHERE incident_id = ?",
                        (keeper_id, duplicate_id),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO incident_criterion (incident_id, incident_type) SELECT ?, incident_type FROM incident_criterion WHERE incident_id = ?",
                        (keeper_id, duplicate_id),
                    )
                connection.executemany(
                    "INSERT OR IGNORE INTO incident_criterion (incident_id, incident_type) VALUES (?, ?)",
                    [(keeper_id, incident_type) for incident_type in criterion_types],
                )
                connection.execute(
                    f"DELETE FROM incident WHERE incident_id IN ({','.join('?' for _ in incident_ids[1:])})",
                    incident_ids[1:],
                )
                request_range = connection.execute(
                    """SELECT MIN(r.start_utc) AS first_seen, MAX(r.start_utc) AS last_seen,
                              COUNT(ir.request_id) AS request_count, COUNT(DISTINCT r.host_id) AS host_count
                       FROM incident_request AS ir JOIN request AS r ON r.request_id = ir.request_id
                       WHERE ir.incident_id = ?""",
                    (keeper_id,),
                ).fetchone()
                host_ids = connection.execute(
                    """SELECT DISTINCT r.host_id FROM incident_request AS ir
                       JOIN request AS r ON r.request_id = ir.request_id
                       WHERE ir.incident_id = ? AND r.host_id IS NOT NULL""",
                    (keeper_id,),
                ).fetchall()
                host_id = host_ids[0]["host_id"] if len(host_ids) == 1 else None
                if request_range["host_count"] > 1:
                    summaries["host_count"] = request_range["host_count"]
                else:
                    summaries.pop("host_count", None)
                indicator_list = sorted(indicators, key=str.casefold)
                metric_count = sum(
                    len(values) for values in summaries.get("criteria", {}).values()
                    if isinstance(values, dict)
                )
                metric_only = not indicator_list and metric_count > 0
                indicator_count = metric_count if metric_only else len(indicator_list)
                connection.execute(
                    """UPDATE incident SET first_seen = COALESCE(?, first_seen), last_seen = COALESCE(?, last_seen),
                           request_count = ?, indicator_count = ?, indicators = ?, summary = ?, host_id = ?, state = ?
                       WHERE incident_id = ?""",
                    (request_range["first_seen"], request_range["last_seen"], request_range["request_count"],
                     indicator_count, json.dumps(indicator_list[:200]), json.dumps(summaries), host_id, merged_state, keeper_id),
                )

    def _queue_incident_merge(self, incident_id: int) -> None:
        self._pending_incident_merges.add(incident_id)

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
