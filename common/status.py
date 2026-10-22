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
        self._write_values({"activity": "Import", "import_file": "", "import_count": "0", "import_files": "[]"})

    def set_import_file(self, path: str) -> None:
        self._write_values({"import_file": path, "last_import_file": path})

    def increment_import_count(self) -> None:
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = ? AND name = 'import_count'",
            (self.GROUP,),
        )
        count = int(rows[0]["value"]) if rows and rows[0]["value"] else 0
        self._write_values({"import_count": str(count + 1)})

    def record_import_file(self, path: str, count: int) -> None:
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = ? AND name = 'import_files'",
            (self.GROUP,),
        )
        try:
            files = json.loads(rows[0]["value"]) if rows and rows[0]["value"] else []
        except (json.JSONDecodeError, TypeError):
            files = []
        if not isinstance(files, list):
            files = []
        for item in files:
            if isinstance(item, dict) and item.get("file") == path:
                item["count"] = int(item.get("count", 0)) + count
                break
        else:
            files.append({"file": path, "count": count})
        self._write_values({"import_files": json.dumps(files, ensure_ascii=False)})

    def set_cowrie_log_available(self, available: bool) -> None:
        self._write_values({"cowrie_log_available": "true" if available else "false"})

    def complete_import(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        self._write_values(
            {
                "last_import": now,
                "activity": "Idle",
                "import_file": "",
                "last_import_files": self._setting_value("import_files", "[]"),
            }
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
        rows = database.query(
            "SELECT name, value FROM settings WHERE group_name = ?",
            (cls.GROUP,),
        )
        values = {row["name"]: row["value"] for row in rows}
        try:
            environment = json.loads(values.get("environment") or "{}")
        except json.JSONDecodeError:
            environment = {}
        try:
            last_import_files = json.loads(values.get("last_import_files") or "[]")
        except json.JSONDecodeError:
            last_import_files = []
        if not isinstance(last_import_files, list):
            last_import_files = []
        return {
            "last_import": values.get("last_import"),
            "activity": values.get("activity", "Idle"),
            "import_file": values.get("import_file", ""),
            "last_import_file": values.get("last_import_file", ""),
            "import_count": int(values.get("import_count") or 0),
            "last_import_files": last_import_files,
            "cowrie_log_available": values.get("cowrie_log_available", "false").lower() == "true",
            "environment": environment,
        }

    def _setting_value(self, name: str, default: str) -> str:
        rows = self.database.query(
            "SELECT value FROM settings WHERE group_name = ? AND name = ?",
            (self.GROUP, name),
        )
        return str(rows[0]["value"]) if rows and rows[0]["value"] is not None else default

    def _write_values(self, values: dict[str, str]) -> None:
        self.database.execute_many(
            """INSERT INTO settings (group_name, name, value) VALUES (?, ?, ?)
               ON CONFLICT(group_name, name) DO UPDATE SET value = excluded.value""",
            [(self.GROUP, name, value) for name, value in values.items()],
        )
