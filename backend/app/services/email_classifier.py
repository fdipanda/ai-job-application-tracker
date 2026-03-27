import re

COMMON_ATS_DOMAINS = [
    "applicantstack",
    "greenhouse",
    "workday",
    "lever",
    "icims",
    "smartrecruiters"
]

RECRUITER_TITLE_SIGNALS = [
    "recruiter",
    "talent acquisition",
    "talent team",
    "talent partner",
    "sourcer",
]

RECRUITER_OUTREACH_SIGNALS = [
    "would love to connect",
    "love to connect",
    "introductory call",
    "schedule a call",
    "book a call",
    "request a call",
    "connect with you",
    "connect regarding",
    "reach out regarding",
    "reach out about",
    "discuss your background",
    "discuss your experience",
    "learn more about your background",
    "next-step discussion",
]

ASSESSMENT_ACTION_SIGNALS = [
    "complete this assessment",
    "complete the assessment",
    "complete your assessment",
    "take the assessment",
    "begin the assessment",
    "start the assessment",
    "complete this coding challenge",
    "complete the coding challenge",
    "complete your coding challenge",
    "complete the hackerrank",
    "complete the codility",
    "take-home assignment",
    "take home assignment",
    "please complete",
]

ASSESSMENT_PLATFORM_SIGNALS = [
    "hackerrank",
    "codility",
    "codesignal",
    "testgorilla",
    "qualified.io",
    "take-home",
    "take home",
    "coding challenge",
    "skill assessment",
]

FUTURE_ASSESSMENT_SIGNALS = [
    "may be sent",
    "may receive",
    "you may receive",
    "may ask you",
    "if selected",
    "if you are selected",
    "next step may include",
    "next steps may include",
    "you may be invited",
    "we may invite you",
    "in the next step",
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
    "unfortunately",
    "pursue other candidates",
    "decided not to move forward",
    "move forward with other candidates",
    "moving forward with other candidates",
    "filled the job with a candidate whose qualifications more closely align",
    "will not be able to explore this role further",
    "we have decided to pursue other candidates",
]

APPLIED_CONFIRMATION_SIGNALS = [
    "we've received your application",
    "we have received your application",
    "thank you for your application",
    "thank you for applying",
    "application received",
    "your application for",
    "we have successfully received your application",
    "we are currently reviewing your application",
    "thanks for applying",
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
]


def classify_email(email):

    text = _email_text(email)

    for status, phrases in STATUS_SIGNALS:
        for phrase in phrases:
            if phrase in text:
                return status

    if _is_assessment_email(text):
        return "Assessment"

    if _contains_any(text, APPLIED_CONFIRMATION_SIGNALS):
        return "Applied"

    if _is_recruiter_contact_email(text):
        return "Recruiter Contact"

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


def _email_text(email):
    return (
        email.get("subject", "")
        + " "
        + email.get("preview", "")
        + " "
        + email.get("body", "")
    ).lower()


def _contains_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def _is_assessment_email(text):
    has_platform_or_assessment = _contains_any(text, ASSESSMENT_PLATFORM_SIGNALS) or "assessment" in text
    if not has_platform_or_assessment:
        return False

    if _contains_any(text, FUTURE_ASSESSMENT_SIGNALS):
        return False

    if _contains_any(text, ASSESSMENT_ACTION_SIGNALS):
        return True

    return any(
        phrase in text
        for phrase in [
            "please use the link below to complete",
            "complete within",
            "submit your take-home",
            "access your assessment",
            "assessment link",
        ]
    )


def _is_recruiter_contact_email(text):
    if _contains_any(text, APPLIED_CONFIRMATION_SIGNALS):
        return False

    has_outreach_signal = _contains_any(text, RECRUITER_OUTREACH_SIGNALS)
    has_recruiter_context = _contains_any(text, RECRUITER_TITLE_SIGNALS)

    if has_outreach_signal:
        return True

    return has_recruiter_context and any(
        phrase in text
        for phrase in [
            "let's connect",
            "lets connect",
            "schedule time",
            "available for a call",
            "speak with you",
            "chat about your background",
        ]
    )
