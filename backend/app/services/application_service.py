import re
from datetime import datetime, timezone
from typing import Optional, Union

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
    # Rebuild the full payload first so shared normalization rules are applied in one place.
    # This is similar to mapping an incoming DTO onto a domain model after validation.
    updates = _build_application_payload(
        {
            "company": update_data.get("company", application.company),
            "role": update_data.get("role", application.role),
            "location": update_data.get("location", application.location),
            "status": update_data.get("status", application.status),
            "application_link": update_data.get("application_link", application.application_link),
            "notes": update_data.get("notes", application.notes),
            "email_subject": update_data.get("email_subject", application.email_subject),
            "sender_email": update_data.get("sender_email", application.sender_email),
            "email_received_at": update_data.get("email_received_at", application.email_received_at),
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
    email_received_at = application_data["email_received_at"]

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

        # Status only moves forward in the hiring pipeline.
        # That prevents a later "thanks for applying" email from downgrading an Interview or Offer.
        if new_rank > current_rank:
            existing.status = status
            did_update = True

        if location and not existing.location:
            existing.location = location
            did_update = True

        did_update = _merge_email_provenance(existing, application_data) or did_update

        if email_received_at and existing.date_applied > email_received_at:
            existing.date_applied = email_received_at
            did_update = True

        if did_update:
            existing.last_updated = datetime.utcnow()

        return existing, "updated" if did_update else "matched"

    # New records use the earliest meaningful date we know about, which might come from the email itself.
    application_data["date_applied"] = _resolve_date_applied(None, email_received_at)
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

    # remove noise words so small wording differences do not create duplicate applications
    filtered = [word for word in words if word not in IGNORED_JOB_KEY_WORDS]

    return "_".join(filtered)


def _build_application_payload(application_data: dict) -> dict:
    company = _normalize_text(application_data.get("company"))
    role = _normalize_text(application_data.get("role"))
    location = _normalize_text(application_data.get("location"))
    email_received_at = _coerce_datetime(application_data.get("email_received_at"))

    return {
        "company": company,
        "role": role,
        "location": location,
        "status": application_data.get("status") or "Applied",
        "application_link": _normalize_text(application_data.get("application_link")),
        "notes": _normalize_text(application_data.get("notes")),
        "email_subject": _normalize_text(application_data.get("email_subject")),
        "sender_email": _normalize_text(application_data.get("sender_email")),
        "email_received_at": email_received_at,
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


def _merge_email_provenance(application: Application, application_data: dict) -> bool:
    did_update = False

    # Only fill subject/sender when they are missing.
    # For received-at we keep the earliest known email because that is most useful for auditing.
    for field_name in ("email_subject", "sender_email"):
        new_value = application_data.get(field_name)
        if new_value and not getattr(application, field_name):
            setattr(application, field_name, new_value)
            did_update = True

    new_received_at = application_data.get("email_received_at")
    if new_received_at and (
        application.email_received_at is None or new_received_at < application.email_received_at
    ):
        application.email_received_at = new_received_at
        did_update = True

    return did_update


def _resolve_date_applied(
    existing_date_applied: Optional[datetime],
    email_received_at: Optional[datetime],
) -> datetime:
    now = _utc_now_naive()
    candidate = existing_date_applied or now

    if email_received_at and email_received_at < candidate:
        candidate = email_received_at

    return candidate


def _coerce_datetime(value: Optional[Union[datetime, str]]) -> Optional[datetime]:
    if value is None or value == "":
        return None

    if isinstance(value, str):
        # Incoming API payloads and email metadata often arrive as ISO strings,
        # so normalize them into datetime objects before persistence.
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    return value


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
