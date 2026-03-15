from sqlalchemy.orm import Session
from app.models import Application
import re

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

IGNORE_WORDS = {
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

def upsert_application(db: Session, parsed_email: dict):

    company = parsed_email.get("company") or ""
    role = parsed_email.get("role") or ""
    location = parsed_email.get("location") or ""
    status = parsed_email.get("status") or "Applied"
    job_key = generate_job_key(company, role)

    if not company or not role:
        return None
    
    # prevent obvious non-jobs
    if len(role) < 4:
        return None
    
    query = db.query(Application).filter(
        Application.company.ilike(company),
        Application.role.ilike(role), Application.job_key == job_key
    )

    if location:
         query = query.filter(Application.location.ilike(location))

    existing = query.first()

    if existing:

        current_rank = STATUS_ORDER.get(existing.status, 0)
        new_rank = STATUS_ORDER.get(status, 0)

        from datetime import datetime

        if new_rank > current_rank:
            existing.status = status
            existing.last_updated = datetime.utcnow()

        return existing

    new_application = Application(
        company=company,
        role=role,
        location=location,
        status=status,
        job_key=job_key
    )

    db.add(new_application)

    return new_application


def generate_job_key(company, role):

    company = (company or "").lower()
    role = (role or "").lower()

    text = f"{company} {role}"

    # remove punctuation
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = text.strip()
    words = text.split()

    # remove noise words
    filtered = [w for w in words if w not in IGNORE_WORDS]

    return "_".join(filtered)