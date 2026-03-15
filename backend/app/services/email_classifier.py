import re

COMMON_ATS_DOMAINS = [
    "applicantstack",
    "greenhouse",
    "workday",
    "lever",
    "icims",
    "smartrecruiters"
]

RECRUITER_CONTACT_SIGNALS = [
    "recruiter",
    "talent acquisition",
    "sourcer",
    "would love to connect",
    "introductory call",
]

ASSESSMENT_SIGNALS = [
    "assessment",
    "coding challenge",
    "take-home",
    "hackerrank",
    "codility",
    "skill assessment",
]

FINAL_INTERVIEW_SIGNALS = [
    "final interview",
    "final round",
    "last interview",
    "meet with the hiring manager",
    "panel interview",
]

INTERVIEW_SIGNALS = [
    "schedule an interview",
    "invite you to interview",
    "interview with our team",
    "interview availability",
    "technical interview",
    "phone screen",
    "screening call",
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

WITHDRAWN_SIGNALS = [
    "application withdrawn",
    "you withdrew",
    "withdrawn from consideration",
    "withdraw your application",
]

STATUS_SIGNALS = [
    ("Withdrawn", WITHDRAWN_SIGNALS),
    ("Offer", OFFER_SIGNALS),
    ("Rejected", REJECTION_SIGNALS),
    ("Final Interview", FINAL_INTERVIEW_SIGNALS),
    ("Interview", INTERVIEW_SIGNALS),
    ("Assessment", ASSESSMENT_SIGNALS),
    ("Recruiter Contact", RECRUITER_CONTACT_SIGNALS),
]


def classify_email(email):

    text = (
        email.get("subject","") +
        email.get("body","")
    ).lower()

    for status, phrases in STATUS_SIGNALS:
        for phrase in phrases:
            if phrase in text:
                return status

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
