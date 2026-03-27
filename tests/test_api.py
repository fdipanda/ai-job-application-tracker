def test_create_get_update_application(client):
    # create
    payload = {
        "company": "Acme",
        "role": "Backend Engineer",
        "status": "Applied",
        "location": "Remote",
        "application_link": None,
        "notes": "Initial"
    }

    resp = client.post("/applications", json=payload)
    assert resp.status_code == 200
    created = resp.json()
    assert created["company"] == "Acme"

    # list
    resp = client.get("/applications")
    assert resp.status_code == 200
    apps = resp.json()
    assert len(apps) >= 1

    app_id = created["id"]

    # update
    update = {"status": "Assessment", "location": "New York"}
    resp = client.put(f"/applications/{app_id}", json=update)
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] == "Assessment"
    assert updated["location"] == "New York"

    # get by id
    resp = client.get(f"/applications/{app_id}")
    assert resp.status_code == 200
    got = resp.json()
    assert got["id"] == app_id


def test_get_application_returns_404_when_missing(client):
    resp = client.get("/applications/999999")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Application not found"}


def test_update_application_returns_404_when_missing(client):
    resp = client.put("/applications/999999", json={"status": "Interview"})

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Application not found"}


def test_process_backlog_returns_409_when_already_running(client):
    import app.main as main

    main.ACCESS_TOKEN = "fake-token"
    acquired = main.EMAIL_SYNC_LOCK.acquire(blocking=False)

    try:
        resp = client.get("/process-backlog")
    finally:
        if acquired:
            main.EMAIL_SYNC_LOCK.release()
        main.ACCESS_TOKEN = None

    assert resp.status_code == 409
    assert resp.json() == {"detail": "Email sync already in progress"}


def test_start_backlog_job_returns_job_id(client, monkeypatch):
    import app.main as main

    started = {}

    class FakeJob:
        job_id = "abc123"
        status = "running"
        max_pages = 20

    main.ACCESS_TOKEN = "fake-token"

    def fake_start_job(**kwargs):
        started.update(kwargs)
        return FakeJob()

    monkeypatch.setattr(main.BACKLOG_JOB_STORE, "start_job", fake_start_job)

    try:
        resp = client.post("/emails/process-backlog", json={"max_pages": 20})
    finally:
        main.ACCESS_TOKEN = None

    assert resp.status_code == 200
    assert resp.json() == {"job_id": "abc123", "status": "running", "max_pages": 20}
    assert started["max_pages"] == 20
    assert started["access_token"] == "fake-token"


def test_get_backlog_job_status_returns_running_payload(client, monkeypatch):
    import app.main as main
    from app.services.backlog_job_service import BacklogJob
    from datetime import datetime, timezone

    monkeypatch.setattr(
        main.BACKLOG_JOB_STORE,
        "get_job",
        lambda job_id: BacklogJob(
            job_id=job_id,
            status="running",
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            max_pages=20,
            pages_processed=6,
            emails_scanned=300,
            applications_processed=18,
            write_failures=0,
            percent_complete=30,
            elapsed_seconds=28,
            eta_seconds=65,
            run_id="run-1",
            audit_log_path="backend/audit/email_audit_run-1.jsonl",
            error_message=None,
        ),
    )

    resp = client.get("/emails/process-backlog/job-123")

    assert resp.status_code == 200
    assert resp.json() == {
        "job_id": "job-123",
        "status": "running",
        "max_pages": 20,
        "pages_processed": 6,
        "emails_scanned": 300,
        "applications_processed": 18,
        "write_failures": 0,
        "percent_complete": 30,
        "elapsed_seconds": 28.0,
        "eta_seconds": 65,
        "run_id": "run-1",
        "audit_log_path": "backend/audit/email_audit_run-1.jsonl",
        "error_message": None,
    }


def test_get_backlog_job_status_returns_completed_summary(client, monkeypatch):
    import app.main as main
    from app.services.backlog_job_service import BacklogJob
    from datetime import datetime, timezone

    monkeypatch.setattr(
        main.BACKLOG_JOB_STORE,
        "get_job",
        lambda job_id: BacklogJob(
            job_id=job_id,
            status="completed",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            max_pages=20,
            pages_processed=20,
            emails_scanned=1000,
            applications_processed=44,
            write_failures=2,
            percent_complete=100,
            elapsed_seconds=90,
            eta_seconds=0,
            run_id="run-2",
            audit_log_path="backend/audit/email_audit_run-2.jsonl",
            error_message=None,
        ),
    )

    resp = client.get("/emails/process-backlog/job-456")

    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["percent_complete"] == 100
    assert resp.json()["applications_processed"] == 44


def test_start_backlog_job_returns_409_when_one_is_already_running(client):
    import app.main as main
    from fastapi import HTTPException

    main.ACCESS_TOKEN = "fake-token"

    def fake_start_job(**kwargs):
        raise HTTPException(status_code=409, detail="Backlog processing is already running")

    main.BACKLOG_JOB_STORE.start_job = fake_start_job

    try:
        resp = client.post("/emails/process-backlog", json={"max_pages": 20})
    finally:
        main.ACCESS_TOKEN = None

    assert resp.status_code == 409
    assert resp.json() == {"detail": "Backlog processing is already running"}
    assert not main.EMAIL_SYNC_LOCK.locked()


def test_sync_new_emails_returns_summary(client, monkeypatch):
    import app.main as main

    main.ACCESS_TOKEN = "fake-token"
    monkeypatch.setattr(
        main,
        "process_new_emails",
        lambda access_token: {
            "scanned_count": 5,
            "detected_count": 2,
            "added_count": 1,
            "updated_count": 1,
            "skipped_count": 3,
            "write_failures": 0,
            "checkpoint_at": None,
            "last_run_status": "success",
        },
    )

    try:
        resp = client.post("/emails/sync-new")
    finally:
        main.ACCESS_TOKEN = None

    assert resp.status_code == 200
    assert resp.json()["scanned_count"] == 5


def test_sync_new_emails_returns_401_and_clears_auth_when_graph_token_is_expired(client, monkeypatch):
    import app.main as main
    from app.services.email_service import GraphAuthenticationError

    cleared = {"called": False}
    main.ACCESS_TOKEN = "stale-token"
    monkeypatch.setattr(main, "process_new_emails", lambda access_token: (_ for _ in ()).throw(GraphAuthenticationError()))
    monkeypatch.setattr(main, "clear_access_token", lambda db: cleared.__setitem__("called", True))

    resp = client.post("/emails/sync-new")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Outlook session expired. Please reconnect."}
    assert main.ACCESS_TOKEN is None
    assert cleared["called"] is True


def test_auth_status_returns_false_when_not_authenticated(client):
    resp = client.get("/auth/status")

    assert resp.status_code == 200
    assert resp.json() == {"authenticated": False}


def test_auth_status_returns_true_when_access_token_is_loaded(client):
    import app.main as main

    main.ACCESS_TOKEN = "fake-token"

    try:
        resp = client.get("/auth/status")
    finally:
        main.ACCESS_TOKEN = None

    assert resp.status_code == 200
    assert resp.json() == {"authenticated": True}


def test_auth_callback_redirects_to_frontend_after_success(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setattr(main, "acquire_token_by_code", lambda code: {"access_token": "fresh-token"})
    monkeypatch.setattr(main, "save_access_token", lambda db, access_token: None)

    class FakeGraphResponse:
        status_code = 200
        text = '{"id":"user-1"}'

    monkeypatch.setattr(main.requests, "get", lambda *args, **kwargs: FakeGraphResponse())

    resp = client.get("/auth/callback?code=abc123", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:3000?outlook=connected"
    assert main.ACCESS_TOKEN == "fresh-token"


def test_auth_callback_redirects_to_frontend_error_when_token_exchange_fails(client, monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setattr(main, "acquire_token_by_code", lambda code: {"error": "invalid_grant"})

    resp = client.get("/auth/callback?code=abc123", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:3000?outlook=error"
