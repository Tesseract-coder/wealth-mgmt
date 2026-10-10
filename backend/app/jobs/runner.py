"""In-process background jobs on a small thread pool, with progress recorded in the Job table.

One job per kind runs at a time: submitting a kind that is already queued/running returns the
existing job instead of starting a duplicate.
"""

import json
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sqlmodel import Session, col, select

from app.core.db import get_engine
from app.models.tables import Job, utcnow

logger = logging.getLogger(__name__)

MAX_ERRORS = 50
ACTIVE = ("queued", "running")


class Progress:
    """Handed to a job function so it can report how far along it is."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        self.errors: list[str] = []

    def update(self, done: int, total: int, message: str | None = None) -> None:
        with Session(get_engine()) as s:
            job = s.get(Job, self.job_id)
            if job:
                job.done, job.total = done, total
                if message is not None:
                    job.message = message
                s.commit()

    def error(self, message: str) -> None:
        self.errors.append(message)
        if len(self.errors) <= MAX_ERRORS:
            with Session(get_engine()) as s:
                job = s.get(Job, self.job_id)
                if job:
                    job.errors = json.dumps(self.errors[:MAX_ERRORS])
                    s.commit()


JobFn = Callable[[Progress], str | None]


class JobRunner:
    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._futures: dict[int, Future[None]] = {}
        self._lock = threading.Lock()

    def submit(
        self, kind: str, fn: JobFn, *, params: dict[str, Any] | None = None, trigger: str = "manual"
    ) -> Job:
        with self._lock, Session(get_engine()) as s:
            existing = s.exec(
                select(Job).where(Job.kind == kind, col(Job.status).in_(ACTIVE))
            ).first()
            if existing:
                return existing
            job = Job(kind=kind, params=json.dumps(params or {}), trigger=trigger)
            s.add(job)
            s.commit()
            s.refresh(job)
            assert job.id is not None
            self._futures[job.id] = self._pool.submit(self._run, job.id, fn)
            return job

    def _run(self, job_id: int, fn: JobFn) -> None:
        with Session(get_engine()) as s:
            job = s.get(Job, job_id)
            assert job is not None
            job.status, job.started_at = "running", utcnow()
            s.commit()
        progress = Progress(job_id)
        try:
            summary = fn(progress)
            status = "done"
        except Exception as e:
            logger.exception("Job %s failed", job_id)
            summary, status = f"Failed: {e}", "failed"
        with Session(get_engine()) as s:
            job = s.get(Job, job_id)
            assert job is not None
            job.status, job.finished_at = status, utcnow()
            if summary is not None:
                job.message = summary
            if progress.errors:
                job.errors = json.dumps(progress.errors[:MAX_ERRORS])
            s.commit()

    def wait(self, job_id: int, timeout: float | None = None) -> None:
        """Block until a job finishes (tests and the CLI use this)."""
        fut = self._futures.get(job_id)
        if fut:
            fut.result(timeout=timeout)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


def mark_interrupted() -> int:
    """Jobs left queued/running by a previous process will never finish; say so."""
    with Session(get_engine()) as s:
        stuck = s.exec(select(Job).where(col(Job.status).in_(ACTIVE))).all()
        for job in stuck:
            job.status, job.finished_at = "failed", utcnow()
            job.message = "Interrupted: the backend restarted before this job finished"
        s.commit()
        return len(stuck)


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def reset_runner() -> None:
    global _runner
    if _runner is not None:
        _runner.shutdown()
    _runner = None
