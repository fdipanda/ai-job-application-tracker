import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database, models
from app.services import application_service, email_service
from app.services.sync_state_service import NEW_EMAIL_SYNC_TYPE


@pytest.fixture
def db_session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session, TestingSessionLocal
    finally:
        session.close()
        engine.dispose()


def test_manual_create_keeps_provenance_optional(db_session):
    session, _ = db_session

    application = application_service.create_application(
        session,
        {
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
        },
    )

    assert application.email_subject is None
    assert application.sender_email is None
    assert application.email_received_at is None
    assert application.date_applied is not None


def test_upsert_new_email_application_sets_provenance_and_earliest_date(db_session):
    session, _ = db_session
    received_at = datetime.now(timezone.utc) - timedelta(days=2)

    application, action = application_service.upsert_application_with_result(
        session,
        {
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
            "location": "Remote",
            "email_subject": "Thanks for applying",
            "sender_email": "jobs@acme.com",
            "email_received_at": received_at.isoformat(),
        },
    )
    session.commit()
    session.refresh(application)

    assert action == "created"
    assert application.email_subject == "Thanks for applying"
    assert application.sender_email == "jobs@acme.com"
    assert application.email_received_at == received_at.replace(tzinfo=None)
    assert application.date_applied == received_at.replace(tzinfo=None)


def test_upsert_existing_application_fills_missing_provenance_and_moves_date_earlier(db_session):
    session, _ = db_session
    existing = application_service.create_application(
        session,
        {
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
        },
    )
    existing.date_applied = datetime.utcnow()
    session.commit()

    earlier_received_at = datetime.now(timezone.utc) - timedelta(days=5)
    application, action = application_service.upsert_application_with_result(
        session,
        {
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Interview",
            "email_subject": "Interview scheduled",
            "sender_email": "recruiting@acme.com",
            "email_received_at": earlier_received_at.isoformat(),
        },
    )
    session.commit()
    session.refresh(application)

    assert action == "updated"
    assert application.id == existing.id
    assert application.status == "Interview"
    assert application.email_subject == "Interview scheduled"
    assert application.sender_email == "recruiting@acme.com"
    assert application.email_received_at == earlier_received_at.replace(tzinfo=None)
    assert application.date_applied == earlier_received_at.replace(tzinfo=None)


def test_upsert_preserves_existing_provenance_when_new_email_is_less_useful(db_session):
    session, _ = db_session
    first_received_at = datetime.now(timezone.utc) - timedelta(days=4)
    application, _ = application_service.upsert_application_with_result(
        session,
        {
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
            "email_subject": "Application received",
            "sender_email": "jobs@acme.com",
            "email_received_at": first_received_at.isoformat(),
        },
    )
    session.commit()
    session.refresh(application)

    later_received_at = datetime.now(timezone.utc) - timedelta(days=1)
    matched, action = application_service.upsert_application_with_result(
        session,
        {
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
            "email_subject": None,
            "sender_email": None,
            "email_received_at": later_received_at.isoformat(),
        },
    )
    session.commit()
    session.refresh(matched)

    assert action == "matched"
    assert matched.email_subject == "Application received"
    assert matched.sender_email == "jobs@acme.com"
    assert matched.email_received_at == first_received_at.replace(tzinfo=None)
    assert matched.date_applied == first_received_at.replace(tzinfo=None)


def test_process_new_emails_writes_audit_file(monkeypatch, tmp_path, db_session):
    session, testing_session_local = db_session
    session.close()

    audit_path = tmp_path / "sync_audit.jsonl"
    message = {
        "id": "msg-1",
        "subject": "Application received",
        "bodyPreview": "Thanks for applying to Acme",
        "body": {"content": "Thanks for applying to Acme for the Backend Engineer role."},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2026-03-19T12:00:00Z",
    }

    monkeypatch.setattr(email_service, "SessionLocal", testing_session_local)
    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [message]})
    monkeypatch.setattr(
        email_service,
        "_initialize_audit_logs",
        lambda sync_type: (audit_path, tmp_path / "email_debug.json", "run-sync"),
    )
    monkeypatch.setattr(
        email_service,
        "_parse_job_email",
        lambda email: (
            {
                "company": "Acme",
                "role": "Backend Engineer",
                "location": "Remote",
                "status": "Applied",
            },
            {"parser": "regex", "ai_failure_reason": None, "raw_ai_output": None},
        ),
    )
    monkeypatch.setattr(
        email_service,
        "classify_job_email",
        lambda email: {"is_job_email": True, "stage": "candidate", "reason": "application_signal:test"},
    )

    summary = email_service.process_new_emails("token", sync_type=NEW_EMAIL_SYNC_TYPE)

    assert summary["audit_log_path"] == str(audit_path)
    assert summary["run_id"] == "run-sync"
    assert audit_path.exists()
    assert Path(summary["debug_log_path"]).name == "email_debug.json"
    assert summary["debug_run_id"] == "run-sync"

    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["sync_type"] == NEW_EMAIL_SYNC_TYPE
    assert record["email_id"] == "msg-1"
    assert record["email_subject"] == "Application received"
    assert record["sender_email"] == "jobs@acme.com"
    assert record["parser_used"] == "regex"
    assert record["action_taken"] == "created"
    assert record["matched_application_id"] is not None
    assert record["resulting_date_applied"] == "2026-03-19T12:00:00"


def test_process_backlog_writes_audit_file(monkeypatch, tmp_path, db_session):
    session, testing_session_local = db_session
    session.close()

    audit_path = tmp_path / "backlog_audit.jsonl"
    message = {
        "id": "msg-2",
        "subject": "Interview update",
        "bodyPreview": "Acme would like to interview you",
        "body": {"content": "Acme would like to interview you for the Backend Engineer position."},
        "from": {"emailAddress": {"address": "recruiting@acme.com"}},
        "receivedDateTime": "2026-03-18T09:30:00Z",
    }

    monkeypatch.setattr(email_service, "SessionLocal", testing_session_local)
    monkeypatch.setattr(email_service, "_fetch_messages_page", lambda url, headers: {"value": [message]})
    monkeypatch.setattr(
        email_service,
        "_initialize_audit_logs",
        lambda sync_type: (audit_path, tmp_path / "email_debug.json", "run-backlog"),
    )
    monkeypatch.setattr(
        email_service,
        "_parse_job_email",
        lambda email: (
            {
                "company": "Acme",
                "role": "Backend Engineer",
                "location": None,
                "status": "Interview",
            },
            {"parser": "ai", "ai_failure_reason": None, "raw_ai_output": None},
        ),
    )
    monkeypatch.setattr(
        email_service,
        "classify_job_email",
        lambda email: {"is_job_email": True, "stage": "candidate", "reason": "job_keyword:interview"},
    )

    result = email_service.process_backlog_emails("token", max_pages=1)

    assert result["audit_log_path"] == str(audit_path)
    assert result["run_id"] == "run-backlog"
    assert result["debug_run_id"] == "run-backlog"
    assert result["applications_processed"] == 1
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["sync_type"] == "backlog"
    assert record["action_taken"] == "created"
    assert record["email_subject"] == "Interview update"


def test_ensure_sqlite_schema_adds_missing_provenance_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE applications (
                    id INTEGER PRIMARY KEY,
                    company VARCHAR NOT NULL,
                    role VARCHAR NOT NULL,
                    status VARCHAR NOT NULL,
                    job_key VARCHAR NOT NULL,
                    location VARCHAR,
                    application_link VARCHAR,
                    notes VARCHAR,
                    date_applied DATETIME,
                    last_updated DATETIME
                )
                """
            )
        )

    monkeypatch.setattr(database, "engine", engine)
    database.ensure_sqlite_schema()

    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(applications)"))
        }

    assert "email_subject" in columns
    assert "sender_email" in columns
    assert "email_received_at" in columns
    engine.dispose()
