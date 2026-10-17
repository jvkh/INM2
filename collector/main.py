"""Application entry point for the Internet Noise Monitor collector."""

from __future__ import annotations

import logging
import os
import signal
import threading
from collections.abc import Callable

import uvicorn

from common.database import Database
from common.env import EnvConfig
from common.logging_setup import configure_file_logging
from common.status import CollectorStatus
from collector.importer import Importer
from collector.control import create_control_app
from collector.maintenance import Maintenance
from collector.scheduler import Scheduler

logger = logging.getLogger(__name__)
CONTROL_PORT = int(os.environ.get("INM2_COLLECTOR_PORT", "8001"))


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
        self._manual_thread: threading.Thread | None = None
        self._control_server: uvicorn.Server | None = None
        self._control_thread: threading.Thread | None = None
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
            self._run_operation("Import", self._import_work, imported=True)

    def _run_maintenance(self) -> None:
        with self._operation_lock:
            self._run_operation("Maintenance", self._maintenance_work)

    def _import_work(self) -> None:
        if self._import_callback is None:
            self.importer.import_logs(
                on_file_start=self.status.set_import_file,
                on_record_imported=self.status.increment_import_count,
            )
        else:
            self._import_callback()

    def _maintenance_work(self) -> None:
        callback = self._maintenance_callback or self.maintenance.run
        callback()

    def _run_operation(self, activity: str, callback: Callable[[], None], *, imported: bool = False) -> None:
        if activity == "Import":
            self.status.begin_import()
        else:
            self.status.begin_maintenance()
        logger.info("%s started", activity)
        try:
            callback()
            if imported:
                self.status.complete_import()
            logger.info("%s completed", activity)
        except Exception:
            logger.exception("%s failed", activity)
            raise
        finally:
            self.status.end_activity()

    def _schedule_manual_operation(
        self, activity: str, callback: Callable[[], None], *, imported: bool = False
    ) -> bool:
        """Reserve the collector and run one manual action in the background."""
        if not self._operation_lock.acquire(blocking=False):
            return False

        try:
            if activity == "Import":
                self.status.begin_import()
            else:
                self.status.begin_maintenance()

            def run_reserved_operation() -> None:
                try:
                    logger.info("Manual %s started", activity.lower())
                    callback()
                    if imported:
                        self.status.complete_import()
                    logger.info("Manual %s completed", activity.lower())
                except Exception:
                    logger.exception("Manually triggered %s failed", activity.lower())
                finally:
                    self.status.end_activity()
                    self._operation_lock.release()

            self._manual_thread = threading.Thread(
                target=run_reserved_operation,
                name=f"manual-{activity.lower()}",
                daemon=True,
            )
            self._manual_thread.start()
        except Exception:
            self.status.end_activity()
            self._operation_lock.release()
            self._manual_thread = None
            raise
        return True

    def request_import(self) -> bool:
        """Start a manual import if no collector operation is active."""
        return self._schedule_manual_operation("Import", self._import_work, imported=True)

    def request_maintenance(self) -> bool:
        """Start manual maintenance if no collector operation is active."""
        return self._schedule_manual_operation("Maintenance", self._maintenance_work)

    def start(self) -> None:
        """Start scheduled work and keep the process alive until interrupted."""
        logger.info("Collector initialized; watching %d log file(s)", len(self.config.log_files))
        self._control_server = uvicorn.Server(
            uvicorn.Config(
                create_control_app(self),
                host="0.0.0.0",
                port=CONTROL_PORT,
                log_level="warning",
            )
        )
        self._control_thread = threading.Thread(
            target=self._control_server.run,
            name="collector-control-api",
            daemon=True,
        )
        self._control_thread.start()
        self.scheduler.start()

    def stop(self) -> None:
        """Stop scheduled work and close the database connection."""
        if self._control_server is not None:
            self._control_server.should_exit = True
        if self._control_thread is not None:
            self._control_thread.join(timeout=5)
        self.scheduler.stop()
        if self._manual_thread is not None:
            self._manual_thread.join()
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
    configure_file_logging("collector")
    try:
        CollectorApplication().run()
    except Exception:
        logger.exception("Collector terminated unexpectedly")
        raise


if __name__ == "__main__":
    main()
