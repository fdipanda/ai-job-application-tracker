import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import requests
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.ai_email_parser import parse_email_with_ai_result
from app.services.application_service import upsert_application_with_result
from app.services.sync_state_service import (
    NEW_EMAIL_SYNC_TYPE,
    mark_sync_finished,
    mark_sync_started,
)

from .email_parser import parse_email
from .job_detector import classify_job_email

GRAPH_API = "https://graph.microsoft.com/v1.0"
logger = logging.getLogger(__name__)
GRAPH_REQUEST_TIMEOUT_SECONDS = 30
LOCK_RETRY_ATTEMPTS = 3
LOCK_RETRY_DELAY_SECONDS = 0.2
MESSAGES_QUERY = (
    f"{GRAPH_API}/me/messages?"
    "$select=subject,bodyPreview,body,from,receivedDateTime,id"
    "&$orderby=receivedDateTime desc"
    "&$top=50"
)


class GraphAuthenticationError(RuntimeError):
    pass


def fetch_recent_emails(access_token):
    db = SessionLocal()

    try:
        processed_emails = []
        next_url = MESSAGES_QUERY
        headers = _build_headers(access_token)

        while next_url:
            data = _fetch_messages_page(next_url, headers)

            for message in data["value"]:
                processed_email = _process_message(db, message)
                if processed_email:
                    processed_emails.append(
                        processed_email
                    )

            next_url = data.get("@odata.nextLink")

        db.commit()
        return processed_emails
    finally:
        db.close()


def process_backlog_emails(
    access_token,
    max_pages=20,
    progress_callback: Optional[Callable[[dict], None]] = None,
):
    # This thin wrapper keeps the public function stable while the actual
    # processing loop lives in a helper that can also report progress.
    return _run_backlog_processing(
        access_token,
        max_pages=max_pages,
        progress_callback=progress_callback,
    )


def _run_backlog_processing(
    access_token,
    max_pages: int,
    progress_callback: Optional[Callable[[dict], None]] = None,
):
    db = SessionLocal()
    audit_log_path, debug_log_path, run_id = _initialize_audit_logs("backlog")

    try:
        pages_processed = 0
        emails_scanned = 0
        applications_processed = 0
        write_failures = 0
        next_url = MESSAGES_QUERY
        headers = _build_headers(access_token)
        started_at = time.monotonic()

        # Emit an initial 0% progress snapshot so the frontend can render immediately.
        _emit_backlog_progress(
            progress_callback,
            started_at=started_at,
            max_pages=max_pages,
            pages_processed=pages_processed,
            emails_scanned=emails_scanned,
            applications_processed=applications_processed,
            write_failures=write_failures,
            run_id=run_id,
            audit_log_path=audit_log_path,
        )

        while next_url and pages_processed < max_pages:
            print(f"Processing page {pages_processed + 1}")
            data = _fetch_messages_page(next_url, headers)
            page_messages = data["value"]
            emails_scanned += len(page_messages)

            for message in page_messages:
                try:
                    did_process = _run_with_write_retry(
                        db,
                        lambda: _process_message(
                            db,
                            message,
                            audit_log_path=audit_log_path,
                            debug_log_path=debug_log_path,
                            audit_run_id=run_id,
                            sync_type="backlog",
                            require_complete_parse=True,
                        ),
                        email_id=message.get("id", "unknown"),
                    )
                except OperationalError as exc:
                    db.rollback()
                    write_failures += 1
                    _append_backlog_error_log(audit_log_path, debug_log_path, run_id, message, exc)
                    logger.warning(
                        "Skipping email %s after SQLite write failure: %s",
                        message.get("id", "unknown"),
                        exc,
                    )
                    continue

                if did_process:
                    applications_processed += 1
                    print(f"Applications detected so far: {applications_processed}")

            next_url = data.get("@odata.nextLink")
            pages_processed += 1
            db.commit()
            print(f"Finished page {pages_processed}")
            # Progress is reported after each page because page count is our most stable unit of work.
            _emit_backlog_progress(
                progress_callback,
                started_at=started_at,
                max_pages=max_pages,
                pages_processed=pages_processed,
                emails_scanned=emails_scanned,
                applications_processed=applications_processed,
                write_failures=write_failures,
                run_id=run_id,
                audit_log_path=audit_log_path,
            )

        db.commit()
        return _build_backlog_summary(
            started_at=started_at,
            max_pages=max_pages,
            pages_processed=pages_processed,
            emails_scanned=emails_scanned,
            applications_processed=applications_processed,
            write_failures=write_failures,
            audit_log_path=str(audit_log_path),
            run_id=run_id,
            debug_log_path=str(debug_log_path),
            debug_run_id=run_id,
        )
    finally:
        db.close()


def process_new_emails(access_token, sync_type: str = NEW_EMAIL_SYNC_TYPE):
    db = SessionLocal()
    audit_log_path, debug_log_path, run_id = _initialize_audit_logs(sync_type)

    try:
        sync_state = mark_sync_started(db, sync_type)
        checkpoint = sync_state.last_email_received_at
        next_url = MESSAGES_QUERY
        headers = _build_headers(access_token)
        scanned_count = 0
        detected_count = 0
        added_count = 0
        updated_count = 0
        skipped_count = 0
        write_failures = 0
        newest_received_at = checkpoint
        run_status = "success"

        while next_url:
            data = _fetch_messages_page(next_url, headers)
            page_messages = data["value"]

            # Once we hit an email older than the saved checkpoint, we can stop.
            # This keeps "sync new" cheap compared to a full backlog scan.
            if checkpoint:
                page_messages, should_stop = _partition_new_messages(page_messages, checkpoint)
            else:
                should_stop = False

            for message in page_messages:
                scanned_count += 1
                message_received_at = _parse_message_received_at(message)
                if message_received_at is None:
                    skipped_count += 1
                    _append_audit_log(
                        audit_log_path,
                        debug_log_path,
                        {
                            "run_id": run_id,
                            "sync_type": sync_type,
                            "email_id": message.get("id"),
                            "email_subject": message.get("subject", ""),
                            "sender_email": (
                                message.get("from", {})
                                .get("emailAddress", {})
                                .get("address")
                            ),
                            "email_received_at": message.get("receivedDateTime"),
                            "detector_reason": None,
                            "parser_used": None,
                            "parsed_company": None,
                            "parsed_role": None,
                            "parsed_location": None,
                            "parsed_status": None,
                            "matched_application_id": None,
                            "action_taken": "skipped",
                            "stage": "skipped",
                            "resulting_date_applied": None,
                            "failure_reason": "missing_receivedDateTime",
                        },
                    )
                    logger.warning(
                        "Skipping malformed Graph message during sync-new because receivedDateTime is missing: %s",
                        message.get("id", "unknown"),
                    )
                    continue

                if newest_received_at is None or message_received_at > _normalize_datetime(newest_received_at):
                    newest_received_at = message_received_at

                try:
                    ingestion_result = _run_with_write_retry(
                        db,
                        lambda: _ingest_message(
                            db,
                            message,
                            audit_log_path=audit_log_path,
                            debug_log_path=debug_log_path,
                            audit_run_id=run_id,
                            sync_type=sync_type,
                            require_complete_parse=True,
                        ),
                        email_id=message.get("id", "unknown"),
                    )
                except OperationalError as exc:
                    db.rollback()
                    write_failures += 1
                    skipped_count += 1
                    run_status = "partial_failure"
                    _append_backlog_error_log(
                        audit_log_path,
                        debug_log_path,
                        run_id,
                        message,
                        exc,
                        sync_type=sync_type,
                    )
                    logger.warning(
                        "Skipping email %s during sync-new after repeated SQLite lock failures: %s",
                        message.get("id", "unknown"),
                        exc,
                    )
                    continue

                if ingestion_result["detected"]:
                    detected_count += 1

                if ingestion_result["action"] == "created":
                    added_count += 1
                elif ingestion_result["action"] == "updated":
                    updated_count += 1
                else:
                    skipped_count += 1

            if should_stop:
                break

            next_url = data.get("@odata.nextLink")

        db.commit()
        finished_state = mark_sync_finished(
            db,
            status=run_status,
            checkpoint_at=newest_received_at,
            sync_type=sync_type,
        )
        return {
            "scanned_count": scanned_count,
            "detected_count": detected_count,
            "added_count": added_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "write_failures": write_failures,
            "checkpoint_at": finished_state.last_email_received_at,
            "last_run_status": finished_state.last_run_status or run_status,
            "audit_log_path": str(audit_log_path),
            "run_id": run_id,
            "debug_log_path": str(debug_log_path),
            "debug_run_id": run_id,
        }
    except Exception:
        db.rollback()
        mark_sync_finished(db, status="failed", sync_type=sync_type)
        raise
    finally:
        db.close()


def _build_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _fetch_messages_page(url: str, headers: dict) -> dict:
    try:
        # requests.get here is the Python equivalent of making an HTTP client call in C#
        # and then validating both the status code and the JSON payload shape.
        response = requests.get(
            url,
            headers=headers,
            timeout=GRAPH_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        if status_code == 401:
            raise GraphAuthenticationError("Microsoft Graph access token expired or is invalid") from exc
        raise RuntimeError(f"Microsoft Graph request failed with status {status_code}") from exc
    except requests.RequestException as exc:
        raise RuntimeError("Microsoft Graph request failed before a response was received") from exc
    except ValueError as exc:
        raise RuntimeError("Microsoft Graph returned invalid JSON") from exc

    if not isinstance(payload, dict) or "value" not in payload or not isinstance(payload["value"], list):
        raise RuntimeError("Microsoft Graph response did not contain the expected message list")

    return payload


def _serialize_message(message: dict) -> dict:
    sender = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address")
    )

    return {
        "subject": message.get("subject", ""),
        "preview": message.get("bodyPreview", ""),
        "body": message.get("body", {}).get("content", ""),
        "sender": sender,
        "received": message.get("receivedDateTime"),
        "id": message.get("id"),
    }


def _initialize_audit_logs(sync_type: str) -> tuple[Path, Path, str]:
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    # We write two files:
    # - a per-run audit log for structured inspection/history
    # - a rolling debug log for quick local inspection tools/workflows
    audit_dir = _resolve_audit_dir()
    audit_log_path = audit_dir / f"email_audit_{run_id}.jsonl"
    _initialize_log_file(audit_log_path)
    debug_log_path = _resolve_debug_log_path()
    _initialize_log_file(debug_log_path)
    return audit_log_path, debug_log_path, run_id


def _parse_job_email(email: dict) -> tuple[Optional[dict], dict]:
    parsed_email, ai_failure = parse_email_with_ai_result(email)
    if parsed_email:
        return parsed_email, {
            "parser": "ai",
            "ai_failure_reason": None,
            "raw_ai_output": None,
        }

    if ai_failure:
        logger.warning(
            "Falling back to regex parsing for email %s after AI parser failure: %s",
            email.get("id", "unknown"),
            ai_failure["reason"],
        )

    # If AI parsing fails, fall back to deterministic regex parsing so the pipeline
    # still produces a best-effort result instead of dropping the email completely.
    return parse_email(email), {
        "parser": "regex",
        "ai_failure_reason": ai_failure["reason"] if ai_failure else None,
        "raw_ai_output": ai_failure.get("raw_output") if ai_failure else None,
    }


def _append_jsonl(log_path: Path, log_entry: dict) -> None:
    with log_path.open("a", encoding="utf-8") as audit_file:
        audit_file.write(json.dumps(log_entry))
        audit_file.write("\n")


def _append_audit_log(audit_log_path: Path, debug_log_path: Optional[Path], log_entry: dict) -> None:
    _append_jsonl(audit_log_path, log_entry)
    if debug_log_path is not None:
        _append_jsonl(debug_log_path, log_entry)


def _append_backlog_error_log(
    audit_log_path: Path,
    debug_log_path: Optional[Path],
    run_id: str,
    message: dict,
    exc: Exception,
    sync_type: str = "backlog",
) -> None:
    email = _serialize_message(message)
    _append_audit_log(
        audit_log_path,
        debug_log_path,
        {
            "run_id": run_id,
            "sync_type": sync_type,
            "email_id": email["id"],
            "email_subject": email["subject"],
            "sender_email": email["sender"],
            "email_received_at": email["received"],
            "detector_reason": None,
            "parser_used": None,
            "parsed_company": None,
            "parsed_role": None,
            "parsed_location": None,
            "parsed_status": None,
            "matched_application_id": None,
            "action_taken": "write_failed",
            "stage": "db_write_failed",
            "resulting_date_applied": None,
            "failure_reason": exc.__class__.__name__,
        },
    )


def _build_debug_entry(
    email: dict,
    run_id: str,
    sync_type: str,
    action: str,
    detector_result: dict,
    parsed_email: Optional[dict] = None,
    parser_details: Optional[dict] = None,
    application=None,
    failure_reason: Optional[str] = None,
) -> dict:
    parsed_email = parsed_email or {}

    return {
        "run_id": run_id,
        "sync_type": sync_type,
        "email_id": email["id"],
        "email_subject": email["subject"],
        "sender_email": email["sender"],
        "email_received_at": email["received"],
        "detector_reason": detector_result["reason"],
        "parser_used": (parser_details or {}).get("parser"),
        "parsed_company": parsed_email.get("company"),
        "parsed_role": parsed_email.get("role"),
        "parsed_location": parsed_email.get("location"),
        "parsed_status": parsed_email.get("status"),
        "matched_application_id": getattr(application, "id", None),
        "action_taken": action,
        "stage": _action_to_stage(action),
        "resulting_date_applied": (
            application.date_applied.isoformat() if getattr(application, "date_applied", None) else None
        ),
        "failure_reason": failure_reason,
    }


def _ingest_message(
    db: Session,
    message: dict,
    audit_log_path: Optional[Path] = None,
    debug_log_path: Optional[Path] = None,
    audit_run_id: Optional[str] = None,
    sync_type: str = "sync_new",
    require_complete_parse: bool = False,
) -> dict:
    email = _serialize_message(message)
    result = {
        "email": email,
        "detected": False,
        "parsed_email": None,
        "application": None,
        "action": "skipped",
    }

    if not _has_required_email_fields(email):
        if audit_log_path and audit_run_id:
            _append_audit_log(
                audit_log_path,
                debug_log_path,
                _build_debug_entry(
                    email,
                    audit_run_id,
                    sync_type,
                    "skipped",
                    {"reason": "missing_required_email_fields"},
                    failure_reason="missing_required_email_fields",
                ),
            )
        logger.warning(
            "Skipping malformed Graph message because required email fields are missing: %s",
            email.get("id") or "unknown",
        )
        return result

    detector_result = classify_job_email(email)
    result["detected"] = detector_result["is_job_email"]

    if not detector_result["is_job_email"]:
        if audit_log_path and audit_run_id:
            _append_audit_log(
                audit_log_path,
                debug_log_path,
                _build_debug_entry(
                    email,
                    audit_run_id,
                    sync_type,
                    "skipped",
                    detector_result,
                ),
            )
        return result

    parsed_email, parser_details = _parse_job_email(email)
    result["parsed_email"] = parsed_email

    if not parsed_email:
        if audit_log_path and audit_run_id:
            _append_audit_log(
                audit_log_path,
                debug_log_path,
                _build_debug_entry(
                    email,
                    audit_run_id,
                    sync_type,
                    "parse_failed",
                    detector_result,
                    parsed_email=None,
                    parser_details=parser_details,
                    failure_reason=parser_details.get("ai_failure_reason"),
                ),
            )
        return result

    if require_complete_parse and (not parsed_email.get("company") or not parsed_email.get("role")):
        if audit_log_path and audit_run_id:
            _append_audit_log(
                audit_log_path,
                debug_log_path,
                _build_debug_entry(
                    email,
                    audit_run_id,
                    sync_type,
                    "skipped",
                    detector_result,
                    parsed_email=parsed_email,
                    parser_details=parser_details,
                    failure_reason="incomplete_parse",
                ),
            )
        return result

    parsed_email = {
        **parsed_email,
        "email_subject": email["subject"],
        "sender_email": email["sender"],
        "email_received_at": email["received"],
    }
    application, action = upsert_application_with_result(db, parsed_email)
    if application is not None and action == "created":
        db.flush()
    result["application"] = application
    result["action"] = action

    if audit_log_path and audit_run_id:
        failure_reason = None if application else "rejected_by_upsert"
        _append_audit_log(
            audit_log_path,
            debug_log_path,
            _build_debug_entry(
                email,
                audit_run_id,
                sync_type,
                action if application else "skipped",
                detector_result,
                parsed_email=parsed_email,
                parser_details=parser_details,
                application=application,
                failure_reason=failure_reason,
            ),
        )

    return result


def _process_message(
    db: Session,
    message: dict,
    audit_log_path: Optional[Path] = None,
    debug_log_path: Optional[Path] = None,
    audit_run_id: Optional[str] = None,
    sync_type: str = "backlog",
    require_complete_parse: bool = False,
):
    ingestion_result = _ingest_message(
        db,
        message,
        audit_log_path=audit_log_path,
        debug_log_path=debug_log_path,
        audit_run_id=audit_run_id,
        sync_type=sync_type,
        require_complete_parse=require_complete_parse,
    )

    if require_complete_parse:
        return ingestion_result["application"] is not None

    if not ingestion_result["application"]:
        return None

    return {
        **ingestion_result["email"],
        **(ingestion_result["parsed_email"] or {}),
    }


def _partition_new_messages(messages: list[dict], checkpoint: datetime) -> tuple[list[dict], bool]:
    new_messages = []
    normalized_checkpoint = _normalize_datetime(checkpoint)

    for message in messages:
        received_at = _parse_graph_datetime(message["receivedDateTime"])
        if received_at <= normalized_checkpoint:
            return new_messages, True
        new_messages.append(message)

    return new_messages, False


def _parse_graph_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_message_received_at(message: dict) -> Optional[datetime]:
    value = message.get("receivedDateTime")
    if not value:
        return None

    return _parse_graph_datetime(value)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def _has_required_email_fields(email: dict) -> bool:
    return bool(email.get("id") and email.get("received") and email.get("sender"))


def _run_with_write_retry(db: Session, operation, email_id: str):
    attempt = 0

    while True:
        try:
            return operation()
        except OperationalError as exc:
            if not _is_sqlite_lock_error(exc) or attempt >= LOCK_RETRY_ATTEMPTS - 1:
                raise

            db.rollback()
            attempt += 1
            logger.warning(
                "Retrying SQLite write for email %s after lock error (%s/%s)",
                email_id,
                attempt,
                LOCK_RETRY_ATTEMPTS - 1,
            )
            time.sleep(LOCK_RETRY_DELAY_SECONDS * attempt)


def _is_sqlite_lock_error(exc: OperationalError) -> bool:
    return "locked" in str(exc).lower()


def _action_to_stage(action: str) -> str:
    if action in {"created", "updated", "matched"}:
        return "persisted"

    if action == "parse_failed":
        return "parse_failed"

    return "skipped"


def _resolve_audit_dir() -> Path:
    candidate_dirs = [
        Path(__file__).resolve().parents[2] / "audit",
        Path(os.getcwd()) / "audit",
        Path(tempfile.gettempdir()) / "ai-job-application-tracker-audit",
    ]

    for candidate_dir in candidate_dirs:
        try:
            candidate_dir.mkdir(parents=True, exist_ok=True)
            probe_path = candidate_dir / ".write_test"
            probe_path.write_text("", encoding="utf-8")
            probe_path.unlink()
            return candidate_dir
        except OSError:
            continue

    raise RuntimeError("Unable to create an audit directory")


def _resolve_debug_log_path() -> Path:
    backend_dir = Path(__file__).resolve().parents[2]
    candidate_paths = [
        backend_dir / "email_debug.json",
        Path(tempfile.gettempdir()) / "ai-job-application-tracker-email_debug.json",
    ]

    for candidate_path in candidate_paths:
        try:
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text("", encoding="utf-8")
            return candidate_path
        except OSError:
            continue

    raise RuntimeError("Unable to create email_debug.json")


def _initialize_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _build_backlog_summary(
    *,
    started_at: float,
    max_pages: int,
    pages_processed: int,
    emails_scanned: int,
    applications_processed: int,
    write_failures: int,
    audit_log_path: str,
    run_id: str,
    debug_log_path: str,
    debug_run_id: str,
) -> dict:
    elapsed_seconds = time.monotonic() - started_at
    percent_complete = calculate_backlog_percent_complete(
        pages_processed=pages_processed,
        max_pages=max_pages,
    )
    eta_seconds = calculate_backlog_eta_seconds(
        elapsed_seconds=elapsed_seconds,
        pages_processed=pages_processed,
        max_pages=max_pages,
    )

    return {
        "max_pages": max_pages,
        "pages_processed": pages_processed,
        "emails_scanned": emails_scanned,
        "applications_processed": applications_processed,
        "write_failures": write_failures,
        "percent_complete": percent_complete,
        "elapsed_seconds": elapsed_seconds,
        "eta_seconds": eta_seconds,
        "audit_log_path": audit_log_path,
        "run_id": run_id,
        "debug_log_path": debug_log_path,
        "debug_run_id": debug_run_id,
    }


def _emit_backlog_progress(
    progress_callback: Optional[Callable[[dict], None]],
    *,
    started_at: float,
    max_pages: int,
    pages_processed: int,
    emails_scanned: int,
    applications_processed: int,
    write_failures: int,
    run_id: str,
    audit_log_path: Path,
) -> None:
    if progress_callback is None:
        return

    elapsed_seconds = time.monotonic() - started_at
    progress_callback(
        {
            "max_pages": max_pages,
            "pages_processed": pages_processed,
            "emails_scanned": emails_scanned,
            "applications_processed": applications_processed,
            "write_failures": write_failures,
            "percent_complete": calculate_backlog_percent_complete(
                pages_processed=pages_processed,
                max_pages=max_pages,
            ),
            "elapsed_seconds": elapsed_seconds,
            "eta_seconds": calculate_backlog_eta_seconds(
                elapsed_seconds=elapsed_seconds,
                pages_processed=pages_processed,
                max_pages=max_pages,
            ),
            "run_id": run_id,
            "audit_log_path": str(audit_log_path),
        }
    )


def calculate_backlog_percent_complete(*, pages_processed: int, max_pages: int) -> int:
    if max_pages <= 0:
        return 0

    percent_complete = int((pages_processed / max_pages) * 100)
    return max(0, min(100, percent_complete))


def calculate_backlog_eta_seconds(
    *,
    elapsed_seconds: float,
    pages_processed: int,
    max_pages: int,
) -> Optional[int]:
    remaining_pages = max(max_pages - pages_processed, 0)
    if remaining_pages == 0:
        return 0

    avg_seconds_per_page = elapsed_seconds / max(pages_processed, 1)
    return max(0, int(avg_seconds_per_page * remaining_pages))
