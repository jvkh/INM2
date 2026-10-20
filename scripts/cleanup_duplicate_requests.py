#!/usr/bin/env python3
"""Find and remove duplicate access-log requests from the INM2 SQLite database.

By default this is a dry run. Pass --apply to create a database backup and
remove duplicate rows, retaining the lowest request_id for each signature.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT_ROOT / "databases" / "inm2.sqlite3"

# Keep this signature in sync with the duplicate check in collector/importer.py.
SIGNATURE_COLUMNS = (
    "actor_id",
    "host_id",
    "start_utc",
    "request_method",
    "request_path",
    "request_scheme",
    "user_agent",
    "downstream_status",
    "downstream_content_size",
    "duration",
)


def duplicate_map_sql() -> str:
    partition = ", ".join(SIGNATURE_COLUMNS)
    return f"""WITH ranked AS (
        SELECT request_id,
               FIRST_VALUE(request_id) OVER (
                   PARTITION BY {partition} ORDER BY request_id
               ) AS keep_id,
               ROW_NUMBER() OVER (
                   PARTITION BY {partition} ORDER BY request_id
               ) AS row_number
        FROM request
    )
    SELECT request_id AS duplicate_id, keep_id
    FROM ranked
    WHERE row_number > 1"""


def counts(connection: sqlite3.Connection) -> tuple[int, int]:
    duplicate_rows = connection.execute(
        f"SELECT COUNT(*) FROM ({duplicate_map_sql()})"
    ).fetchone()[0]
    duplicate_groups = connection.execute(
        f"SELECT COUNT(*) FROM (SELECT 1 FROM ({duplicate_map_sql()}) GROUP BY keep_id)"
    ).fetchone()[0]
    return int(duplicate_rows), int(duplicate_groups)


def create_backup(connection: sqlite3.Connection, database_path: Path) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(f"{database_path.name}.before-dedup-{timestamp}")
    target = sqlite3.connect(backup_path)
    try:
        connection.backup(target)
    finally:
        target.close()
    return backup_path


def remove_duplicates(connection: sqlite3.Connection) -> int:
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("DROP TABLE IF EXISTS temp.duplicate_request_map")
        connection.execute(
            f"CREATE TEMP TABLE duplicate_request_map AS {duplicate_map_sql()}"
        )
        duplicate_count = int(
            connection.execute("SELECT COUNT(*) FROM duplicate_request_map").fetchone()[0]
        )
        if duplicate_count == 0:
            connection.commit()
            return 0

        # Preserve category and incident links on the retained request. A request
        # can belong to only one burst; INSERT OR IGNORE keeps its existing link
        # if the duplicate happened to be assigned to a different burst.
        connection.execute(
            """INSERT OR IGNORE INTO request_category (request_id, category_id)
               SELECT m.keep_id, rc.category_id
               FROM request_category AS rc
               JOIN duplicate_request_map AS m ON m.duplicate_id = rc.request_id"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO incident_request (incident_id, request_id)
               SELECT ir.incident_id, m.keep_id
               FROM incident_request AS ir
               JOIN duplicate_request_map AS m ON m.duplicate_id = ir.request_id"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO burst_request (request_id, burst_id)
               SELECT m.keep_id, br.burst_id
               FROM burst_request AS br
               JOIN duplicate_request_map AS m ON m.duplicate_id = br.request_id"""
        )
        connection.execute(
            """DELETE FROM request
               WHERE request_id IN (SELECT duplicate_id FROM duplicate_request_map)"""
        )

        # Recalculate stored burst counters after duplicate memberships cascade away.
        connection.execute("DELETE FROM burst WHERE burst_id NOT IN (SELECT burst_id FROM burst_request)")
        connection.execute("DELETE FROM burst_category")
        connection.execute(
            """UPDATE burst
               SET start_time = (SELECT MIN(r.start_utc) FROM burst_request br JOIN request r USING (request_id) WHERE br.burst_id = burst.burst_id),
                   end_time = (SELECT MAX(r.start_utc) FROM burst_request br JOIN request r USING (request_id) WHERE br.burst_id = burst.burst_id),
                   read_count = (SELECT COUNT(*) FROM burst_request br JOIN request r USING (request_id) WHERE br.burst_id = burst.burst_id AND upper(r.request_method) IN ('GET','HEAD','OPTIONS')),
                   write_count = (SELECT COUNT(*) FROM burst_request br JOIN request r USING (request_id) WHERE br.burst_id = burst.burst_id AND upper(r.request_method) IN ('POST','PUT','PATCH','DELETE')),
                   other_count = (SELECT COUNT(*) FROM burst_request br JOIN request r USING (request_id) WHERE br.burst_id = burst.burst_id AND upper(COALESCE(r.request_method,'')) NOT IN ('GET','HEAD','OPTIONS','POST','PUT','PATCH','DELETE')),
                   avg_count = (SELECT COUNT(*) * 1.0 / MAX((julianday(MAX(r.start_utc)) - julianday(MIN(r.start_utc))) * 86400.0, 1.0)
                                FROM burst_request br JOIN request r USING (request_id) WHERE br.burst_id = burst.burst_id)"""
        )
        connection.execute(
            """INSERT INTO burst_category (burst_id, category_id, request_count)
               SELECT br.burst_id, rc.category_id, COUNT(*)
               FROM burst_request br
               JOIN request_category rc ON rc.request_id = br.request_id
               GROUP BY br.burst_id, rc.category_id"""
        )
        connection.execute(
            """UPDATE incident
               SET request_count = (SELECT COUNT(*) FROM incident_request ir WHERE ir.incident_id = incident.incident_id),
                   first_seen = COALESCE((SELECT MIN(r.start_utc) FROM incident_request ir JOIN request r USING (request_id) WHERE ir.incident_id = incident.incident_id), first_seen),
                   last_seen = COALESCE((SELECT MAX(r.start_utc) FROM incident_request ir JOIN request r USING (request_id) WHERE ir.incident_id = incident.incident_id), last_seen)"""
        )
        connection.commit()
        return duplicate_count
    except BaseException:
        connection.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, default=DEFAULT_DATABASE,
        help=f"SQLite database path (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="create a backup, then delete duplicates (default is a read-only preview)",
    )
    args = parser.parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        parser.error(f"database file not found: {database_path}")

    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        duplicate_rows, duplicate_groups = counts(connection)
        print(f"Database: {database_path}")
        print(f"Duplicate groups: {duplicate_groups:,}")
        print(f"Rows to remove (larger request_id): {duplicate_rows:,}")
        if not args.apply:
            print("Dry run only. No rows were changed. Use --apply to back up and delete.")
            return 0
        if duplicate_rows == 0:
            print("No duplicate requests found.")
            return 0

        backup_path = create_backup(connection, database_path)
        print(f"Backup created: {backup_path}")
        removed = remove_duplicates(connection)
        print(f"Removed {removed:,} duplicate request rows; kept the lowest request_id in each group.")
        print("Burst and incident request links and stored counts were updated in the same transaction.")
        return 0
    except sqlite3.Error as exc:
        print(f"Database cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
