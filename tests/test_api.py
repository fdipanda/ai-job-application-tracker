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
