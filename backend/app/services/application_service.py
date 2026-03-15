import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Application

STATUS_ORDER = {
    "Wishlist": 0,
    "Applied": 1,
    "Recruiter Contact": 2,
    "Assessment": 3,
    "Interview": 4,
    "Final Interview": 5,
    "Offer": 6,
    "Rejected": 7,
    "Withdrawn": 8
}

IGNORED_JOB_KEY_WORDS = {
    "remote",
    "onsite",
    "hybrid",
    "summer",
    "fall",
    "spring",
    "2024",
    "2025",
    "2026"
}


def create_application(db: Session, application_data: dict) -> Application:
    payload = _build_application_payload(application_data)
    application = Application(**payload)
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def list_applications(db: Session) -> list[Application]:
    return db.query(Application).all()


def get_application_by_id(db: Session, application_id: int) -> Optional[Application]:
    return db.query(Application).filter(Application.id == application_id).first()


def update_application(db: Session, application: Application, update_data: dict) -> Application:
    updates = _build_application_payload(
        {
            "company": update_data.get("company", application.company),
            "role": update_data.get("role", application.role),
            "location": update_data.get("location", application.location),
            "status": update_data.get("status", application.status),
            "application_link": update_data.get("application_link", application.application_link),
            "notes": update_data.get("notes", application.notes),
        }
    )

    for field_name, field_value in update_data.items():
        setattr(application, field_name, updates[field_name])

    if "company" in update_data or "role" in update_data:
        application.job_key = updates["job_key"]

    application.last_updated = datetime.utcnow()

    db.commit()
    db.refresh(application)
    return application


def delete_application(db: Session, application: Application) -> None:
    db.delete(application)
    db.commit()


def upsert_application(db: Session, parsed_email: dict) -> Optional[Application]:
    application, _ = upsert_application_with_result(db, parsed_email)
    return application


def upsert_application_with_result(db: Session, parsed_email: dict) -> tuple[Optional[Application], str]:
    application_data = _build_application_payload(parsed_email)
    company = application_data["company"]
    role = application_data["role"]
    location = application_data["location"]
    status = application_data["status"]
    job_key = application_data["job_key"]

    if not company or not role:
        return None, "skipped"
    
    # prevent obvious non-jobs
    if len(role) < 4:
        return None, "skipped"
    
    db.flush()
    matches = db.query(Application).filter(Application.job_key == job_key).all()
    existing = _select_existing_application(matches, location)

    if existing:
        did_update = False
        current_rank = STATUS_ORDER.get(existing.status, 0)
        new_rank = STATUS_ORDER.get(status, 0)

        if new_rank > current_rank:
            existing.status = status
            did_update = True

        if location and not existing.location:
            existing.location = location
            did_update = True

        if did_update:
            existing.last_updated = datetime.utcnow()

        return existing, "updated" if did_update else "matched"

    new_application = Application(**application_data)

    db.add(new_application)

    return new_application, "created"


def generate_job_key(company: str, role: str) -> str:

    company = (company or "").lower()
    role = (role or "").lower()

    text = f"{company} {role}"

    # remove punctuation
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = text.strip()
    words = text.split()

    # remove noise words
    filtered = [word for word in words if word not in IGNORED_JOB_KEY_WORDS]

    return "_".join(filtered)


def _build_application_payload(application_data: dict) -> dict:
    company = _normalize_text(application_data.get("company"))
    role = _normalize_text(application_data.get("role"))
    location = _normalize_text(application_data.get("location"))

    return {
        "company": company,
        "role": role,
        "location": location,
        "status": application_data.get("status") or "Applied",
        "application_link": _normalize_text(application_data.get("application_link")),
        "notes": _normalize_text(application_data.get("notes")),
        "job_key": generate_job_key(company, role),
    }


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None


def _select_existing_application(
    matches: list[Application],
    location: Optional[str],
) -> Optional[Application]:
    if not matches:
        return None

    if location:
        for application in matches:
            if application.location and application.location.lower() == location.lower():
                return application

    for application in matches:
        if not application.location:
            return application

    return matches[0]
