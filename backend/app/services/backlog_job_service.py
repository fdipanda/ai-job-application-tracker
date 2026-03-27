from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Callable, Optional
from uuid import uuid4

from fastapi import HTTPException


@dataclass
class BacklogJob:
    job_id: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    max_pages: int
    pages_processed: int
    emails_scanned: int
    applications_processed: int
    write_failures: int
    percent_complete: int
    elapsed_seconds: float
    eta_seconds: Optional[int]
    run_id: Optional[str]
    audit_log_path: Optional[str]
    error_message: Optional[str]


class BacklogJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, BacklogJob] = {}
        self._active_job_id: Optional[str] = None
        self._lock = Lock()

    def start_job(
        self,
        *,
        max_pages: int,
        access_token: str,
        runner: Callable[..., dict],
        release_sync_lock: Callable[[], None],
    ) -> BacklogJob:
        with self._lock:
            # The store allows only one active backlog job at a time.
            # That keeps UI progress reporting simple and avoids fighting over the sync lock.
            if self._active_job_id is not None:
                active_job = self._jobs[self._active_job_id]
                if active_job.status == "running":
                    raise HTTPException(
                        status_code=409,
                        detail="Backlog processing is already running",
                    )

            job = BacklogJob(
                job_id=uuid4().hex,
                status="running",
                started_at=_utcnow(),
                finished_at=None,
                max_pages=max_pages,
                pages_processed=0,
                emails_scanned=0,
                applications_processed=0,
                write_failures=0,
                percent_complete=0,
                elapsed_seconds=0,
                eta_seconds=None,
                run_id=None,
                audit_log_path=None,
                error_message=None,
            )
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id

        def run() -> None:
            # The actual work happens on a background thread so the API can return immediately
            # and the frontend can poll for progress.
            try:
                summary = runner(
                    access_token,
                    max_pages=max_pages,
                    progress_callback=lambda progress: self.update_job(job.job_id, **progress),
                )
                self.complete_job(job.job_id, summary)
            except Exception as exc:
                self.fail_job(job.job_id, str(exc))
            finally:
                release_sync_lock()

        Thread(target=run, daemon=True).start()
        return job

    def get_job(self, job_id: str) -> BacklogJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Backlog job not found")
            return BacklogJob(**asdict(job))

    def update_job(self, job_id: str, **updates) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in updates.items():
                setattr(job, key, value)
            # elapsed_seconds should only move forward even if an out-of-order update arrives.
            job.elapsed_seconds = max(job.elapsed_seconds, updates.get("elapsed_seconds", 0))

    def complete_job(self, job_id: str, summary: dict) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in summary.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.status = "completed"
            job.percent_complete = 100
            job.eta_seconds = 0
            job.finished_at = _utcnow()
            self._active_job_id = None

    def fail_job(self, job_id: str, error_message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "failed"
            job.error_message = error_message
            job.finished_at = _utcnow()
            job.percent_complete = min(max(job.percent_complete, 0), 100)
            job.eta_seconds = None
            self._active_job_id = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
