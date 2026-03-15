import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

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


def process_backlog_emails(access_token, max_pages=20):
    db = SessionLocal()
    debug_log_path = os.path.join(os.getcwd(), "email_debug.json")
    run_id = _initialize_debug_log(debug_log_path)

    try:
        pages_processed = 0
        applications_processed = 0
        write_failures = 0
        next_url = MESSAGES_QUERY
        headers = _build_headers(access_token)

        while next_url and pages_processed < max_pages:
            print(f"Processing page {pages_processed + 1}")
            data = _fetch_messages_page(next_url, headers)

            for message in data["value"]:
                try:
                    did_process = _run_with_write_retry(
                        db,
                        lambda: _process_message(
                            db,
                            message,
                            debug_log_path=debug_log_path,
                            debug_run_id=run_id,
                            require_complete_parse=True,
                        ),
                        email_id=message.get("id", "unknown"),
                    )
                except OperationalError as exc:
                    db.rollback()
                    write_failures += 1
                    _append_backlog_error_log(debug_log_path, run_id, message, exc)
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

        db.commit()
        return {
            "pages_processed": pages_processed,
            "applications_processed": applications_processed,
            "write_failures": write_failures,
            "debug_log_path": debug_log_path,
            "debug_run_id": run_id,
        }
    finally:
        db.close()


def process_new_emails(access_token, sync_type: str = NEW_EMAIL_SYNC_TYPE):
    db = SessionLocal()

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

            if checkpoint:
                page_messages, should_stop = _partition_new_messages(page_messages, checkpoint)
            else:
                should_stop = False

            for message in page_messages:
                scanned_count += 1
                message_received_at = _parse_message_received_at(message)
                if message_received_at is None:
                    skipped_count += 1
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
                        lambda: _ingest_message(db, message, require_complete_parse=True),
                        email_id=message.get("id", "unknown"),
                    )
                except OperationalError as exc:
                    db.rollback()
                    write_failures += 1
                    skipped_count += 1
                    run_status = "partial_failure"
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
        response = requests.get(
            url,
            headers=headers,
            timeout=GRAPH_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
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


def _initialize_debug_log(log_path: str) -> str:
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    with open(log_path, "w") as debug_file:
        debug_file.write("")
    return run_id


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

    return parse_email(email), {
        "parser": "regex",
        "ai_failure_reason": ai_failure["reason"] if ai_failure else None,
        "raw_ai_output": ai_failure.get("raw_output") if ai_failure else None,
    }


def _append_debug_log(log_path: str, log_entry: dict) -> None:
    with open(log_path, "a") as debug_file:
        debug_file.write(json.dumps(log_entry))
        debug_file.write("\n")


def _append_backlog_error_log(log_path: str, run_id: str, message: dict, exc: Exception) -> None:
    email = _serialize_message(message)
    _append_debug_log(
        log_path,
        {
            "run_id": run_id,
            "email_id": email["id"],
            "received": email["received"],
            "subject": email["subject"],
            "sender": email["sender"],
            "stage": "db_write_failed",
            "detector_reason": None,
            "parsed": None,
            "parser_details": {
                "parser": None,
                "ai_failure_reason": None,
                "raw_ai_output": None,
            },
            "error": exc.__class__.__name__,
        },
    )


def _build_debug_entry(
    email: dict,
    run_id: str,
    stage: str,
    detector_result: dict,
    parsed_email: Optional[dict] = None,
    parser_details: Optional[dict] = None,
) -> dict:
    return {
        "run_id": run_id,
        "email_id": email["id"],
        "received": email["received"],
        "subject": email["subject"],
        "sender": email["sender"],
        "stage": stage,
        "detector_reason": detector_result["reason"],
        "parsed": parsed_email,
        "parser_details": parser_details or {
            "parser": None,
            "ai_failure_reason": None,
            "raw_ai_output": None,
        },
    }


def _ingest_message(
    db: Session,
    message: dict,
    debug_log_path: Optional[str] = None,
    debug_run_id: Optional[str] = None,
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
        logger.warning(
            "Skipping malformed Graph message because required email fields are missing: %s",
            email.get("id") or "unknown",
        )
        return result

    detector_result = classify_job_email(email)
    result["detected"] = detector_result["is_job_email"]

    if not detector_result["is_job_email"]:
        return result

    parsed_email, parser_details = _parse_job_email(email)
    result["parsed_email"] = parsed_email

    if not parsed_email:
        if debug_log_path and debug_run_id:
            _append_debug_log(
                debug_log_path,
                _build_debug_entry(
                    email,
                    debug_run_id,
                    "parse_failed",
                    detector_result,
                    parsed_email=None,
                    parser_details=parser_details,
                ),
            )
        return result

    if require_complete_parse and (not parsed_email.get("company") or not parsed_email.get("role")):
        if debug_log_path and debug_run_id:
            _append_debug_log(
                debug_log_path,
                _build_debug_entry(
                    email,
                    debug_run_id,
                    "incomplete_parse",
                    detector_result,
                    parsed_email=parsed_email,
                    parser_details=parser_details,
                ),
            )
        return result

    application, action = upsert_application_with_result(db, parsed_email)
    result["application"] = application
    result["action"] = action

    if debug_log_path and debug_run_id:
        stage = "persisted" if application else "rejected_by_upsert"
        _append_debug_log(
            debug_log_path,
            _build_debug_entry(
                email,
                debug_run_id,
                stage,
                detector_result,
                parsed_email=parsed_email,
                parser_details=parser_details,
            ),
        )

    return result


def _process_message(
    db: Session,
    message: dict,
    debug_log_path: Optional[str] = None,
    debug_run_id: Optional[str] = None,
    require_complete_parse: bool = False,
):
    ingestion_result = _ingest_message(
        db,
        message,
        debug_log_path=debug_log_path,
        debug_run_id=debug_run_id,
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
