"""Application entry point for the Internet Noise Monitor collector."""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable

from common.database import Database
from common.env import EnvConfig
from common.status import CollectorStatus
from collector.importer import Importer
from collector.maintenance import Maintenance
from collector.scheduler import Scheduler

logger = logging.getLogger(__name__)


class CollectorApplication:
    """Initialize shared services and control the collector scheduler."""

    def __init__(
        self,
        config: EnvConfig | None = None,
        database: Database | None = None,
        *,
        import_callback: Callable[[], None] | None = None,
        maintenance_callback: Callable[[], None] | None = None,
    ) -> None:
        self.config = config or EnvConfig()
        self.database = database or Database()
        self.importer = Importer(self.config, self.database)
        self.maintenance = Maintenance(self.config, self.database)
        self.status = CollectorStatus(self.database, self.config)
        self._operation_lock = threading.Lock()
        self._import_callback = import_callback
        self._maintenance_callback = maintenance_callback
        self.scheduler = Scheduler()
        self.scheduler.add_job(
            "import-logs",
            self.config.input_interval_seconds,
            self._run_import,
        )
        self.scheduler.add_job(
            "maintenance",
            self.config.maintenance_interval_days * 24 * 60 * 60,
            self._run_maintenance,
        )

    def _run_import(self) -> None:
        with self._operation_lock:
            self.status.begin_import()
            try:
                if self._import_callback is None:
                    self.importer.import_logs(
                        on_file_start=self.status.set_import_file,
                        on_record_imported=self.status.increment_import_count,
                    )
                else:
                    self._import_callback()
                self.status.complete_import()
            finally:
                self.status.end_activity()

    def _run_maintenance(self) -> None:
        with self._operation_lock:
            self.status.begin_maintenance()
            try:
                callback = self._maintenance_callback or self.maintenance.run
                callback()
            finally:
                self.status.end_activity()

    def start(self) -> None:
        """Start scheduled work and keep the process alive until interrupted."""
        logger.info("Collector initialized; watching %d log file(s)", len(self.config.log_files))
        self.scheduler.start()

    def stop(self) -> None:
        """Stop scheduled work and close the database connection."""
        self.scheduler.stop()
        self.importer.close()
        self.database.close()

    def run(self) -> None:
        """Run until SIGINT or SIGTERM is received."""
        stopped = threading.Event()

        def request_stop(signum: int, frame: object) -> None:
            logger.info("Received signal %s; shutting down", signum)
            stopped.set()

        previous_sigint = signal.signal(signal.SIGINT, request_stop)
        previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
        try:
            self.start()
            stopped.wait()
        finally:
            self.stop()
            signal.signal(signal.SIGINT, previous_sigint)
            signal.signal(signal.SIGTERM, previous_sigterm)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    CollectorApplication().run()


if __name__ == "__main__":
    main()
