from app.services import application_service as svc
from app.models import Application


def test_upsert_duplicate_location_and_status_upgrade(db_session):
    parsed1 = {
        "company": "Acme Service Test",
        "role": "Backend Engineer",
        "location": None,
        "status": "Applied",
        "application_link": None,
        "notes": None,
    }

    # first upsert should create a new application (added to session)
    first = svc.upsert_application(db_session, parsed1)
    assert isinstance(first, Application)

    # commit so it is persisted and has an id
    db_session.commit()

    matching_rows = (
        db_session.query(Application)
        .filter(Application.company == "Acme Service Test", Application.role == "Backend Engineer")
        .all()
    )
    assert len(matching_rows) == 1

    # now upsert with a higher-status and added location
    parsed2 = parsed1.copy()
    parsed2.update({"status": "Assessment", "location": "New York"})

    second = svc.upsert_application(db_session, parsed2)

    # Should return the existing application with updated fields
    assert second is not None
    assert second.status == "Assessment"
    assert second.location == "New York"

    # a no-op update (lower rank) should not downgrade status
    parsed3 = parsed1.copy()
    parsed3.update({"status": "Applied", "location": None})

    third = svc.upsert_application(db_session, parsed3)
    assert third.status == "Assessment"


def test_generate_job_key_filters_noise():
    key = svc.generate_job_key("Acme", "Backend Engineer")
    assert "acme" in key
    assert "backend" in key
