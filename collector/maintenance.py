"""Scheduled cleanup for retained honeypot data and inactive actors."""

from __future__ import annotations

import os
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common.database import Database
from common.env import EnvConfig

logger = logging.getLogger(__name__)


class Maintenance:
    """Remove expired Cowrie source logs and inactive actors."""

    def __init__(self, config: EnvConfig, database: Database) -> None:
        self.config = config
        self.database = database

    def delete_inactive_actors(self) -> int:
        """Delete stale source IPs and their data unless explicitly excluded."""
        inactive_days = self.config.maintenance_inactive_days
        if inactive_days < 0:
            raise ValueError("MAINTENANCE_INACTIVE_DAYS must not be negative")

        cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)
        cutoff_text = cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
        body_directory = Path(os.environ.get("HONEYPOT_BODY_DIR", "/logs/honeypot-bodies"))
        with self.database.transaction() as connection:
            stale_ips = [row[0] for row in connection.execute(
                """SELECT ip FROM (
                       SELECT ip, MAX(last_time) AS last_time FROM (
                           SELECT ip, last_time FROM actor
                           UNION ALL SELECT client_ip, time FROM honeypot_event WHERE client_ip IS NOT NULL
                           UNION ALL SELECT src_ip, time FROM cowrie_event WHERE src_ip IS NOT NULL
                       ) GROUP BY ip
                   ) AS activity
                   WHERE julianday(last_time) < julianday(?)
                     AND ip NOT IN (SELECT ip FROM maintenance_exclusion)""",
                (cutoff_text,),
            ).fetchall()]
            if not stale_ips:
                return 0
            connection.execute("CREATE TEMP TABLE IF NOT EXISTS stale_maintenance_ip (ip TEXT PRIMARY KEY)")
            connection.execute("DELETE FROM stale_maintenance_ip")
            connection.executemany("INSERT INTO stale_maintenance_ip(ip) VALUES (?)", ((ip,) for ip in stale_ips))
            bodies = connection.execute(
                "SELECT event_id, body_file FROM honeypot_event WHERE client_ip IN (SELECT ip FROM stale_maintenance_ip)"
            ).fetchall()
            web_count = connection.execute(
                "DELETE FROM honeypot_event WHERE client_ip IN (SELECT ip FROM stale_maintenance_ip)"
            ).rowcount
            cowrie_count = connection.execute(
                "DELETE FROM cowrie_event WHERE src_ip IN (SELECT ip FROM stale_maintenance_ip)"
            ).rowcount
            actor_count = connection.execute(
                "DELETE FROM actor WHERE ip IN (SELECT ip FROM stale_maintenance_ip)"
            ).rowcount
        for row in bodies:
            if row["body_file"] == f"{row['event_id']}.bin":
                try:
                    (body_directory / row["body_file"]).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not delete inactive Web Honeypot body %s", row["body_file"])

        logger.info("Maintenance deleted %d inactive actor(s), %d Cowrie event(s), and %d Web Honeypot event(s)", actor_count, cowrie_count, web_count)
        return actor_count + cowrie_count + web_count

    def delete_old_cowrie_logs(self) -> int:
        """Delete date-rotated Cowrie logs older than the configured retention.

        The active JSON file is never removed. A retention value of zero
        disables deletion. Only Cowrie's recognized date-suffixed log names
        are eligible; TTY recordings and downloaded artifacts are untouched.
        """
        enabled = (self.config.get("COWRIE_ENABLED", "false") or "false").strip().lower()
        if enabled not in {"1", "true", "yes", "on"}:
            return 0

        retention_days = self.config.maintenance_log_retention_days
        if retention_days == 0:
            logger.info("Cowrie log cleanup is disabled (MAINTENANCE_LOG_RETENTION_DAYS=0)")
            return 0

        log_path = Path(self.config.get("COWRIE_LOG_PATH", "/cowrie-logs/cowrie.json") or "/cowrie-logs/cowrie.json")
        log_directory = log_path.parent
        if not log_directory.is_dir():
            logger.warning("Cowrie log directory %s is not accessible; skipping log cleanup", log_directory)
            return 0

        prefixes = {log_path.name, "cowrie.log"}
        rotated_patterns = [
            re.compile(rf"^{re.escape(prefix)}-\d{{4}}-\d{{1,2}}-\d{{1,2}}\.log$")
            for prefix in prefixes
        ] + [
            re.compile(rf"^{re.escape(prefix)}\.\d{{4}}_\d{{2}}_\d{{2}}$")
            for prefix in prefixes
        ]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp()
        deleted = 0
        try:
            candidates = list(log_directory.iterdir())
        except OSError:
            logger.exception("Could not list Cowrie log directory %s", log_directory)
            return 0
        for path in candidates:
            if path.is_symlink() or not path.is_file() or not any(pattern.fullmatch(path.name) for pattern in rotated_patterns):
                continue
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
                path.unlink()
                deleted += 1
            except OSError:
                logger.exception("Could not delete expired Cowrie log %s", path)

        logger.info("Maintenance deleted %d expired Cowrie log file(s)", deleted)
        return deleted

    def delete_expired_honeypot_events(self) -> int:
        """Delete old Web Honeypot events and their external body files."""
        retention_days = self.config.maintenance_log_retention_days
        if retention_days == 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_text = cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
        body_directory = Path(os.environ.get("HONEYPOT_BODY_DIR", "/logs/honeypot-bodies"))
        with self.database.transaction() as connection:
            expired = connection.execute(
                """SELECT event_id, body_file FROM honeypot_event
                   WHERE julianday(time) < julianday(?)
                     AND (client_ip IS NULL OR client_ip NOT IN (SELECT ip FROM maintenance_exclusion))""",
                (cutoff_text,),
            ).fetchall()
            connection.execute(
                """DELETE FROM honeypot_event WHERE julianday(time) < julianday(?)
                   AND (client_ip IS NULL OR client_ip NOT IN (SELECT ip FROM maintenance_exclusion))""",
                (cutoff_text,),
            )
        for row in expired:
            event_id, body_file = row["event_id"], row["body_file"]
            if body_file == f"{event_id}.bin":
                try:
                    (body_directory / body_file).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not delete expired Web Honeypot body %s", body_file)
        deleted = len(expired)
        logger.info("Maintenance deleted %d expired Web Honeypot event(s)", deleted)
        return deleted

    def delete_expired_cowrie_events(self) -> int:
        """Delete old Cowrie events from the INM2 database."""
        retention_days = self.config.maintenance_log_retention_days
        if retention_days == 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_text = cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """DELETE FROM cowrie_event WHERE julianday(time) < julianday(?)
                   AND (src_ip IS NULL OR src_ip NOT IN (SELECT ip FROM maintenance_exclusion))""",
                (cutoff_text,),
            )
            deleted = cursor.rowcount
        logger.info("Maintenance deleted %d expired Cowrie event(s) from INM2", deleted)
        return deleted

    def run(self) -> int:
        """Run configured log, event, and actor cleanup."""
        deleted_logs = self.delete_old_cowrie_logs()
        deleted_events = self.delete_expired_honeypot_events() + self.delete_expired_cowrie_events()
        deleted_actors = self.delete_inactive_actors()
        return deleted_logs + deleted_events + deleted_actors
