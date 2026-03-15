import re

COMMON_ATS_DOMAINS = [
    "applicantstack",
    "greenhouse",
    "workday",
    "lever",
    "icims",
    "smartrecruiters"
]

INTERVIEW_SIGNALS = [
    "schedule an interview",
    "invite you to interview",
    "interview with our team",
    "interview availability",
    "technical interview"
]

OFFER_SIGNALS = [
    "offer letter",
    "pleased to offer",
    "extend an offer",
    "formal offer"
]

REJECTION_SIGNALS = [
    "not moving forward",
    "after careful consideration",
    "we regret to inform you",
    "unfortunately"
]


def classify_email(email):

    text = (
        email.get("subject","") +
        email.get("body","")
    ).lower()

    for phrase in OFFER_SIGNALS:
        if phrase in text:
            return "Offer"

    for phrase in INTERVIEW_SIGNALS:
        if phrase in text:
            return "Interview"

    for phrase in REJECTION_SIGNALS:
        if phrase in text:
            return "Rejected"

    return "Applied"

def extract_company(email):

    text = email["subject"] + " " + email["preview"]

    # Try to find company after phrases like:
    patterns = [
        r"at ([A-Z][A-Za-z0-9& ]+)",
        r"with ([A-Z][A-Za-z0-9& ]+)",
        r"from ([A-Z][A-Za-z0-9& ]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    # fallback to sender domain
    sender = email["sender"]
    domain = sender.split("@")[-1].split(".")[0]

    if domain not in COMMON_ATS_DOMAINS:
        return domain.capitalize()

    return "Unknown Company"