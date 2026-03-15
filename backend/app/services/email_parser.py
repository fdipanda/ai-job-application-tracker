import re
from .email_classifier import classify_email

def parse_email(email):

    text = (
    email["subject"]
    + " "
    + email["preview"]
    + " "
    + email["body"]
)
    
    text = re.sub("<.*?>", " ", text)
    text = text.replace("\n", " ")

    company = extract_company(text)
    role = extract_role(text)
    location = extract_location(text)
    status = classify_email(email)

    return {
        "company": company,
        "role": role,
        "location": location,
        "status": status
    }

def extract_company(text):

    patterns = [
        r"at ([A-Z][A-Za-z0-9& ]+)",
        r"with ([A-Z][A-Za-z0-9& ]+)",
        r"from ([A-Z][A-Za-z0-9& ]+)"
    ]

    for p in patterns:
        match = re.search(p, text)
        if match:
            return match.group(1).strip()

    return None

def extract_role(text):

    patterns = [
        r"for the ([A-Za-z0-9 ]+) position",
        r"for the ([A-Za-z0-9 ]+) role",
        r"for ([A-Za-z0-9 ]+) at",
        r"position: ([A-Za-z0-9 ]+)"
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None

def extract_location(text):

    patterns = [
        r"location[: ]+([A-Za-z ,]+)",
        r"in ([A-Z][A-Za-z ,]+)"
    ]

    for p in patterns:
        match = re.search(p, text)
        if match:
            return match.group(1).strip()

    return None