"""Small dependency-free interval scheduler for collector jobs."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class Scheduler:
    """Run registered callbacks repeatedly on a background thread."""

    def __init__(self) -> None:
        self._jobs: list[tuple[str, float, Callable[[], None]]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def add_job(self, name: str, interval_seconds: float, callback: Callable[[], None]) -> None:
        """Register a callback to run once per interval."""
        if interval_seconds <= 0:
            raise ValueError("Job interval must be greater than zero")
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Cannot add jobs after the scheduler has started")
        if any(existing_name == name for existing_name, _, _ in self._jobs):
            raise ValueError(f"A job named {name!r} is already registered")
        self._jobs.append((name, interval_seconds, callback))

    def start(self) -> None:
        """Start the scheduler in the background; safe to call only once."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="collector-scheduler", daemon=True)
        self._thread.start()
        logger.info("Scheduler started with %d job(s)", len(self._jobs))

    def stop(self, timeout: float | None = None) -> None:
        """Request shutdown and wait for the scheduler thread to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        now = time.monotonic()
        next_run = [
            (name, interval, callback, now)
            for name, interval, callback in self._jobs
        ]
        while not self._stop_event.is_set():
            now = time.monotonic()
            due_jobs = [job for job in next_run if job[3] <= now]

            for name, interval, callback, _due in due_jobs:
                if self._stop_event.is_set():
                    return
                try:
                    callback()
                except Exception:
                    logger.exception("Scheduled job '%s' failed", name)

                next_due = time.monotonic() + interval
                next_run = [
                    (job_name, job_interval, job_callback,
                     next_due if job_name == name else due)
                    for job_name, job_interval, job_callback, due in next_run
                ]

            if not next_run:
                self._stop_event.wait()
                continue

            seconds_until_next_job = max(
                0.0, min(job[3] for job in next_run) - time.monotonic()
            )
            self._stop_event.wait(seconds_until_next_job)
