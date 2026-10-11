"""Persist collector runtime status for readers such as the API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from common.database import Database
from common.env import EnvConfig


class CollectorStatus:
    """Store and expose status values through the shared ``settings`` table."""

    GROUP = "collector_status"

    def __init__(self, database: Database, config: EnvConfig) -> None:
        self.database = database
        self.config = config
        self._write_values(
            {
                "activity": "Idle",
                "import_file": "",
                "environment": json.dumps(config.as_dict(), ensure_ascii=False),
            }
        )

    def begin_import(self) -> None:
        self._write_values({"activity": "Import", "import_file": "", "import_count": "0"})

    def set_import_file(self, path: str) -> None:
        self._write_values({"import_file": path, "last_import_file": path})

    def increment_import_count(self) -> None:
        row = self.database.connection.execute(
            "SELECT value FROM settings WHERE group_name = ? AND name = 'import_count'",
            (self.GROUP,),
        ).fetchone()
        count = int(row[0]) if row and row[0] else 0
        self._write_values({"import_count": str(count + 1)})

    def complete_import(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self._write_values(
            {"last_import": now, "activity": "Idle", "import_file": ""}
        )

    def begin_maintenance(self) -> None:
        self._write_values({"activity": "Maintenance", "import_file": ""})

    def end_activity(self) -> None:
        self._write_values({"activity": "Idle", "import_file": ""})

    def snapshot(self) -> dict[str, Any]:
        """Return the current status as a JSON-ready dictionary."""
        return self.read_snapshot(self.database)

    @classmethod
    def read_snapshot(cls, database: Database) -> dict[str, Any]:
        """Read the stored collector status without changing it."""
        rows = database.connection.execute(
            "SELECT name, value FROM settings WHERE group_name = ?",
            (cls.GROUP,),
        ).fetchall()
        values = {row["name"]: row["value"] for row in rows}
        try:
            environment = json.loads(values.get("environment") or "{}")
        except json.JSONDecodeError:
            environment = {}
        return {
            "last_import": values.get("last_import"),
            "activity": values.get("activity", "Idle"),
            "import_file": values.get("import_file", ""),
            "last_import_file": values.get("last_import_file", ""),
            "import_count": int(values.get("import_count") or 0),
            "environment": environment,
        }

    def _write_values(self, values: dict[str, str]) -> None:
        with self.database.connection:
            self.database.connection.executemany(
                """INSERT INTO settings (group_name, name, value) VALUES (?, ?, ?)
                   ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value""",
                [(self.GROUP, name, value) for name, value in values.items()],
            )
