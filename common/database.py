"""SQLite database access and initialization for the collector."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "databases" / "inm2.sqlite3"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "common" / "scripts" / "init.sql"


class Database:
    """Manage the application's SQLite database.

    The default database is ``databases/inm2.sqlite3`` at the project root.
    It is created and initialized from ``common/scripts/init.sql`` on first
    use. SQL parameters should be passed separately rather than interpolated
    into query strings.
    """

    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
        schema_path: str | Path = DEFAULT_SCHEMA_PATH,
        *,
        initialize: bool = True,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.schema_path = Path(schema_path).expanduser().resolve()
        self._lock = RLock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        # Scheduled importer callbacks run on the scheduler thread.
        # The API and collector use separate connections to the same SQLite
        # file. WAL lets API readers continue while the collector is writing,
        # and the longer busy timeout absorbs short write-lock contention
        # during imports and burst updates.
        self.connection = sqlite3.connect(
            self.database_path,
            timeout=30.0,
            check_same_thread=False,
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 30000")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
        self.connection.execute("PRAGMA foreign_keys = ON")
        if initialize:
            self.initialize()

    def initialize(self) -> None:
        """Create missing tables and indexes using the schema SQL file."""
        if not self.schema_path.is_file():
            raise FileNotFoundError(f"Database schema not found: {self.schema_path}")
        with self._lock:
            self.connection.executescript(self.schema_path.read_text(encoding="utf-8"))
            self.connection.commit()

    def execute(
        self,
        sql: str,
        parameters: Sequence[Any] | dict[str, Any] = (),
    ) -> sqlite3.Cursor:
        """Execute an INSERT, UPDATE, DELETE, or other SQL statement."""
        with self._lock:
            cursor = self.connection.execute(sql, parameters)
            self.connection.commit()
            return cursor

    def execute_many(
        self,
        sql: str,
        parameters: Sequence[Sequence[Any]],
    ) -> sqlite3.Cursor:
        """Execute a batch of writes atomically against the shared connection."""
        with self._lock:
            cursor = self.connection.executemany(sql, parameters)
            self.connection.commit()
            return cursor

    def query(
        self,
        sql: str,
        parameters: Sequence[Any] | dict[str, Any] = (),
    ) -> list[dict[str, Any]]:
        """Execute a query and return its rows as a list of dictionaries."""
        with self._lock:
            cursor = self.connection.execute(sql, parameters)
            return [dict(row) for row in cursor.fetchall()]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a multi-statement transaction while holding this connection lock."""
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                self.connection.rollback()
                raise
            else:
                self.connection.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self.connection.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        if exc_type is not None:
            self.connection.rollback()
        self.close()
