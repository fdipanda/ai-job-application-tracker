import re

from .email_classifier import classify_email

MAX_COMPANY_LENGTH = 60
MAX_LOCATION_LENGTH = 80
GENERIC_COMPANY_SUFFIXES = (
    " careers",
    " career",
    " jobs",
    " job alerts",
)
COMPANY_STOP_PHRASES = (
    "thank you",
    "newsletter",
    "weekly digest",
)


def parse_email(email):
    text = _normalize_text(
        email["subject"]
        + " "
        + email["preview"]
        + " "
        + email["body"]
    )

    company = extract_company(text)
    role = extract_role(text)
    location = extract_location(text)
    status = classify_email(email)

    return {
        "company": company,
        "role": role,
        "location": location,
        "status": status,
    }


def extract_company(text):
    patterns = [
        r"\bat ([A-Z][A-Za-z0-9&,' .-]+?)(?:[.!?:;\n]| for\b| role\b| position\b| in\b|$)",
        r"\bwith ([A-Z][A-Za-z0-9&,' .-]+?)(?:[.!?:;\n]| for\b| role\b| position\b| in\b|$)",
        r"\bfrom ([A-Z][A-Za-z0-9&,' .-]+?)(?:[.!?:;\n]| for\b| role\b| position\b| in\b|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            company = _clean_company(match.group(1))
            if company:
                return company

    return None


def extract_role(text):
    patterns = [
        r"for the ([A-Za-z0-9 /-]+?) position",
        r"for the ([A-Za-z0-9 /-]+?) role",
        r"for ([A-Za-z0-9 /-]+?) at",
        r"position: ([A-Za-z0-9 /-]+?)(?:[.!?:;\n]| at\b| in\b|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            role = _clean_field(match.group(1), max_length=80)
            if role:
                return role

    return None


def extract_location(text):
    patterns = [
        r"location[: ]+([A-Za-z ,.-]+?)(?:[.!?;\n]|$)",
        r"\bin ([A-Z][A-Za-z ,.-]+?)(?:[.!?;\n]| with\b| for\b|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            location = _clean_location(match.group(1))
            if location:
                return location

    return None


def _normalize_text(value):
    text = re.sub(r"<.*?>", " ", value)
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _clean_company(value):
    company = _clean_field(value, max_length=MAX_COMPANY_LENGTH)
    if not company:
        return None

    company = re.split(r"\b(?:hi|hello|dear)\b", company, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    company = _trim_generic_suffixes(company)

    lowered = company.lower()
    if not company or any(phrase in lowered for phrase in COMPANY_STOP_PHRASES):
        return None

    return company


def _clean_location(value):
    location = _clean_field(value, max_length=MAX_LOCATION_LENGTH)
    if not location:
        return None

    lowered = location.lower()
    if "thank you" in lowered or "careers" in lowered:
        return None

    return location


def _clean_field(value, max_length):
    cleaned = re.split(r"[|<>]", value, maxsplit=1)[0]
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:;-")

    if not cleaned or len(cleaned) > max_length:
        return None

    return cleaned


def _trim_generic_suffixes(company):
    cleaned = company

    for suffix in GENERIC_COMPANY_SUFFIXES:
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip(" ,.:;-")

    return cleaned
