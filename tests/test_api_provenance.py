def test_create_application_rejects_manual_provenance_fields(client):
    payload = {
        "company": "Acme",
        "role": "Backend Engineer",
        "status": "Applied",
        "email_subject": "Should be rejected",
    }

    resp = client.post("/applications", json=payload)

    assert resp.status_code == 422


def test_update_application_rejects_manual_provenance_fields(client):
    create_resp = client.post(
        "/applications",
        json={
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
        },
    )
    app_id = create_resp.json()["id"]

    resp = client.put(
        f"/applications/{app_id}",
        json={"sender_email": "jobs@acme.com"},
    )

    assert resp.status_code == 422


def test_application_response_includes_optional_provenance_fields(client):
    resp = client.post(
        "/applications",
        json={
            "company": "Acme",
            "role": "Backend Engineer",
            "status": "Applied",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "email_subject" in body
    assert "sender_email" in body
    assert "email_received_at" in body
    assert body["email_subject"] is None
