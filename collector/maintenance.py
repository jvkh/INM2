"""Database cleanup for actors that have been inactive for too long."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from common.database import Database
from common.env import EnvConfig

logger = logging.getLogger(__name__)


class Maintenance:
    """Remove inactive actors and their dependent records."""

    def __init__(self, config: EnvConfig, database: Database) -> None:
        self.config = config
        self.database = database

    def delete_inactive_actors(self) -> int:
        """Delete actors older than the configured inactivity window.

        Foreign-key cascades remove each actor's requests, request-category
        links, bursts, and burst-category links in the same transaction.
        Returns the number of deleted actors.
        """
        inactive_days = self.config.maintenance_inactive_days
        if inactive_days < 0:
            raise ValueError("MAINTENANCE_INACTIVE_DAYS must not be negative")

        cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)
        cutoff_text = cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
        with self.database.connection:
            cursor = self.database.connection.execute(
                "DELETE FROM actor WHERE last_time < ?", (cutoff_text,)
            )
            deleted = cursor.rowcount

        logger.info("Maintenance deleted %d inactive actor(s)", deleted)
        return deleted

    def run(self) -> int:
        """Run the configured actor cleanup."""
        return self.delete_inactive_actors()
