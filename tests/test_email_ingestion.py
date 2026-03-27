import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.services import email_service
from app.services import sync_state_service
from app.models import Application, SyncState
from sqlalchemy.exc import OperationalError
import requests


def test_fetch_recent_emails_uses_fetch_page_and_process(monkeypatch, db_session):
    # simulate one page with two messages
    sample_message = {
        "subject": "Thanks for applying to Acme",
        "bodyPreview": "preview",
        "body": {"content": "We received your application for Backend Engineer at Acme"},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "id": "1",
    }

    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [sample_message],})

    # replace SessionLocal so the service uses our test session
    email_service.SessionLocal = lambda: db_session

    # monkeypatch parse to return parsed payload so fetch_recent_emails collects it
    monkeypatch.setattr(email_service, "_process_message", lambda db, message: {"dummy": True})

    processed = email_service.fetch_recent_emails("fake-token")

    assert isinstance(processed, list)
    assert processed == [{"dummy": True}]


def test_process_backlog_respects_require_complete_parse(monkeypatch, db_session):
    # message missing role/company should be skipped when require_complete_parse=True
    incomplete_message = {
        "subject": "Hello",
        "bodyPreview": "preview",
        "body": {"content": "This is not a job"},
        "from": {"emailAddress": {"address": "noreply@newsletter.com"}},
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "id": "2",
    }

    # first call returns one page
    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [incomplete_message],})

    email_service.SessionLocal = lambda: db_session

    # force AI parser to return parse without company/role
    monkeypatch.setattr(email_service, "parse_email_with_ai_result", lambda email: ({"company": None, "role": None, "status": "Applied"}, None))

    result = email_service.process_backlog_emails("token", max_pages=1)

    assert "pages_processed" in result
    assert result["applications_processed"] == 0


def test_process_backlog_recreates_debug_log_and_skips_filtered_messages(monkeypatch, db_session, tmp_path):
    db_session.query(Application).delete()
    db_session.commit()

    messages = [
        {
            "subject": "Your Timesheet Received",
            "bodyPreview": "Week Ending 2026-03-07",
            "body": {"content": "Your timesheet for Week Ending 2026-03-07 has been received."},
            "from": {"emailAddress": {"address": "admin@consulting.example.com"}},
            "receivedDateTime": "2026-03-08T00:00:00Z",
            "id": "filtered-1",
        },
        {
            "subject": "Thanks for applying to Acme",
            "bodyPreview": "preview",
            "body": {"content": "We received your application for Backend Engineer at Acme."},
            "from": {"emailAddress": {"address": "jobs@acme.com"}},
            "receivedDateTime": "2026-03-08T00:01:00Z",
            "id": "job-1",
        },
    ]

    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": messages})
    monkeypatch.setattr(
        email_service,
        "parse_email_with_ai_result",
        lambda email: ({"company": "Acme", "role": "Backend Engineer", "location": None, "status": "Applied"}, None),
    )
    email_service.SessionLocal = lambda: db_session

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    debug_log_path = backend_dir / "email_debug.json"
    debug_log_path.write_text("old log contents")

    monkeypatch.setattr(
        email_service,
        "_resolve_debug_log_path",
        lambda: debug_log_path,
    )
    monkeypatch.chdir(backend_dir)

    result = email_service.process_backlog_emails("token", max_pages=1)

    log_lines = debug_log_path.read_text().strip().splitlines()
    assert result["applications_processed"] == 1
    assert result["debug_log_path"] == str(debug_log_path)
    assert result["debug_run_id"] == result["run_id"]
    assert len(log_lines) == 2

    filtered_entry = json.loads(log_lines[0])
    assert filtered_entry["email_id"] == "filtered-1"
    assert filtered_entry["action_taken"] == "skipped"
    assert filtered_entry["stage"] == "skipped"

    log_entry = json.loads(log_lines[1])
    assert log_entry["email_id"] == "job-1"
    assert log_entry["stage"] == "persisted"
    assert log_entry["action_taken"] in {"created", "updated"}
    assert log_entry["run_id"] == result["debug_run_id"]
    assert log_entry["sync_type"] == "backlog"
    assert log_entry["email_subject"] == "Thanks for applying to Acme"
    assert log_entry["sender_email"] == "jobs@acme.com"
    assert log_entry["email_received_at"] == "2026-03-08T00:01:00Z"
    assert log_entry["detector_reason"] is not None
    assert log_entry["parser_used"] == "ai"
    assert log_entry["parsed_company"] == "Acme"
    assert log_entry["parsed_role"] == "Backend Engineer"
    assert log_entry["parsed_location"] is None
    assert log_entry["parsed_status"] == "Applied"
    assert log_entry["matched_application_id"] is not None
    assert log_entry["resulting_date_applied"] == "2026-03-08T00:01:00"
    assert log_entry["failure_reason"] is None

    audit_lines = Path(result["audit_log_path"]).read_text().strip().splitlines()
    assert len(audit_lines) == 2


def test_process_backlog_records_write_failures_without_crashing(monkeypatch, db_session, tmp_path):
    sample_message = {
        "subject": "Thanks for applying to Acme",
        "bodyPreview": "preview",
        "body": {"content": "We received your application for Backend Engineer at Acme."},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2026-03-08T00:01:00Z",
        "id": "job-locked",
    }

    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [sample_message]})
    monkeypatch.setattr(
        email_service,
        "_process_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(OperationalError("insert", {}, Exception("locked"))),
    )
    email_service.SessionLocal = lambda: db_session

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    debug_log_path = backend_dir / "email_debug.json"
    monkeypatch.setattr(
        email_service,
        "_resolve_debug_log_path",
        lambda: debug_log_path,
    )
    monkeypatch.chdir(backend_dir)

    result = email_service.process_backlog_emails("token", max_pages=1)

    log_lines = debug_log_path.read_text().strip().splitlines()
    assert result["write_failures"] == 1
    assert len(log_lines) == 1
    log_entry = json.loads(log_lines[0])
    assert log_entry["stage"] == "db_write_failed"
    assert log_entry["action_taken"] == "write_failed"
    assert log_entry["failure_reason"] == "OperationalError"


def test_process_new_emails_uses_checkpoint_and_updates_sync_state(monkeypatch, db_session):
    newer_message = {
        "subject": "Thanks for applying to Acme",
        "bodyPreview": "preview",
        "body": {"content": "We received your application for Backend Engineer at Acme."},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2026-03-10T12:00:00Z",
        "id": "new-1",
    }
    older_message = {
        "subject": "Old email",
        "bodyPreview": "preview",
        "body": {"content": "Old content"},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2026-03-08T12:00:00Z",
        "id": "old-1",
    }

    state = sync_state_service.get_sync_state(db_session)
    state.last_email_received_at = datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [newer_message, older_message]})
    monkeypatch.setattr(
        email_service,
        "_ingest_message",
        lambda db, message, **kwargs: {
            "email": {"id": message["id"]},
            "detected": True,
            "parsed_email": {"company": "Acme", "role": "Backend Engineer"},
            "application": object(),
            "action": "created",
        },
    )
    email_service.SessionLocal = lambda: db_session

    result = email_service.process_new_emails("token")

    refreshed = db_session.query(SyncState).filter(SyncState.sync_type == sync_state_service.NEW_EMAIL_SYNC_TYPE).first()
    assert result["scanned_count"] == 1
    assert result["detected_count"] == 1
    assert result["added_count"] == 1
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 0
    assert result["write_failures"] == 0
    assert refreshed.last_run_status == "success"
    assert refreshed.last_email_received_at == datetime(2026, 3, 10, 12, 0)
    assert result["debug_run_id"] == result["run_id"]
    assert result["debug_log_path"].endswith("email_debug.json")


def test_process_new_emails_reports_write_failures_without_advancing_checkpoint(monkeypatch, db_session):
    newer_message = {
        "subject": "Thanks for applying to Acme",
        "bodyPreview": "preview",
        "body": {"content": "We received your application for Backend Engineer at Acme."},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2026-03-10T12:00:00Z",
        "id": "new-locked",
    }

    state = sync_state_service.get_sync_state(db_session)
    state.last_email_received_at = datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
    db_session.commit()

    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [newer_message]})
    monkeypatch.setattr(
        email_service,
        "_ingest_message",
        lambda db, message, **kwargs: (_ for _ in ()).throw(OperationalError("insert", {}, Exception("locked"))),
    )
    email_service.SessionLocal = lambda: db_session

    result = email_service.process_new_emails("token")

    refreshed = db_session.query(SyncState).filter(SyncState.sync_type == sync_state_service.NEW_EMAIL_SYNC_TYPE).first()
    assert result["write_failures"] == 1
    assert result["skipped_count"] == 1
    assert result["last_run_status"] == "partial_failure"
    assert refreshed.last_email_received_at == datetime(2026, 3, 9, 0, 0)


def test_process_new_emails_skips_malformed_messages_without_failing(monkeypatch, db_session):
    malformed_message = {
        "subject": "System message",
        "bodyPreview": "preview",
        "body": {"content": "Missing sender"},
        "receivedDateTime": "2026-03-10T12:00:00Z",
        "id": "malformed-1",
    }
    valid_message = {
        "subject": "Thanks for applying to Acme",
        "bodyPreview": "preview",
        "body": {"content": "We received your application for Backend Engineer at Acme."},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2026-03-10T11:00:00Z",
        "id": "valid-1",
    }

    original_ingest_message = email_service._ingest_message

    monkeypatch.setattr(
        email_service,
        "_fetch_messages_page",
        lambda url, headers: {"value": [malformed_message, valid_message]},
    )
    monkeypatch.setattr(
        email_service,
        "_ingest_message",
        lambda db, message, **kwargs: {
            "email": {"id": message["id"]},
            "detected": message["id"] == "valid-1",
            "parsed_email": {"company": "Acme", "role": "Backend Engineer"},
            "application": object() if message["id"] == "valid-1" else None,
            "action": "created" if message["id"] == "valid-1" else "skipped",
        } if message["id"] == "valid-1" else original_ingest_message(db, message, **kwargs),
    )
    email_service.SessionLocal = lambda: db_session

    result = email_service.process_new_emails("token")

    assert result["scanned_count"] == 2
    assert result["detected_count"] == 1
    assert result["added_count"] == 1
    assert result["skipped_count"] == 1
    assert result["write_failures"] == 0


def test_fetch_messages_page_raises_clear_error_for_graph_failure(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            raise requests.HTTPError(response=SimpleNamespace(status_code=429))

    monkeypatch.setattr(email_service.requests, "get", lambda *args, **kwargs: FakeResponse())

    try:
        email_service._fetch_messages_page("https://graph.test", {})
    except RuntimeError as exc:
        assert "status 429" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for failed Graph request")
