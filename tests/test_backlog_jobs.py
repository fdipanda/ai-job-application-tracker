from app.services.backlog_job_service import BacklogJobStore
from app.services.email_service import (
    calculate_backlog_eta_seconds,
    calculate_backlog_percent_complete,
)
from fastapi import HTTPException
from threading import Event
import time


def test_calculate_backlog_percent_complete_clamps_to_range():
    assert calculate_backlog_percent_complete(pages_processed=6, max_pages=20) == 30
    assert calculate_backlog_percent_complete(pages_processed=25, max_pages=20) == 100
    assert calculate_backlog_percent_complete(pages_processed=1, max_pages=0) == 0


def test_calculate_backlog_eta_seconds_uses_average_page_time():
    assert calculate_backlog_eta_seconds(
        elapsed_seconds=28,
        pages_processed=6,
        max_pages=20,
    ) == 65
    assert calculate_backlog_eta_seconds(
        elapsed_seconds=90,
        pages_processed=20,
        max_pages=20,
    ) == 0


def test_backlog_job_store_prevents_simultaneous_jobs():
    store = BacklogJobStore()
    started = Event()
    release_runner = Event()
    finished = Event()

    def completed_summary():
        return {
            "max_pages": 20,
            "pages_processed": 20,
            "emails_scanned": 1000,
            "applications_processed": 40,
            "write_failures": 0,
            "percent_complete": 100,
            "elapsed_seconds": 90,
            "eta_seconds": 0,
            "run_id": "run-1",
            "audit_log_path": "audit.jsonl",
            "debug_log_path": "debug.json",
            "debug_run_id": "run-1",
        }

    def runner(*args, **kwargs):
        started.set()
        release_runner.wait(timeout=2)
        return completed_summary()

    job = store.start_job(
        max_pages=20,
        access_token="token",
        runner=runner,
        release_sync_lock=finished.set,
    )
    assert started.wait(timeout=2)

    try:
        try:
            store.start_job(
                max_pages=20,
                access_token="token",
                runner=runner,
                release_sync_lock=lambda: None,
            )
            assert False, "Expected a 409 when starting a second backlog job"
        except HTTPException as exc:
            assert exc.status_code == 409
    finally:
        release_runner.set()

    assert finished.wait(timeout=2)
    time.sleep(0.05)
    finished_job = store.get_job(job.job_id)
    assert finished_job.status == "completed"
