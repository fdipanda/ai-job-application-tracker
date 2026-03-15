JOB_KEYWORDS = [
    "application",
    "interview",
    "assessment",
    "coding challenge",
    "recruiter",
    "career",
    "talent",
    "position",
    "thank you for applying",
]

NEGATIVE_KEYWORDS = [
    "loan",
    "credit",
    "statement",
    "payment",
    "invoice",
    "receipt",
    "bank",
    "account",
    "subscription",
    "newsletter",
    "promotion",
]

CONSULTING_ADMIN_SIGNALS = [
    "timesheet",
    "week ending",
    "submitted hours",
    "approved hours",
    "payroll",
    "expense report",
    "invoice submission",
    "billing",
]

BLOCKED_SENDERS = [
    "linkedin.com",
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "notifications@ripplematch.com",
    "glassdoor.com",
    "indeed.com",
]

APPLICATION_SIGNALS = [
    "application received",
    "thanks for applying",
    "thank you for applying",
    "your application",
    "we received your application",
    "confirm that your application",
]


def classify_job_email(email):
    sender = email.get("sender", "").lower()

    for blocked in BLOCKED_SENDERS:
        if blocked in sender:
            return {
                "is_job_email": False,
                "stage": "filtered",
                "reason": f"blocked_sender:{blocked}",
            }

    text = (
        email.get("subject", "") +
        email.get("preview", "") +
        email.get("body", "")
    ).lower()

    for phrase in CONSULTING_ADMIN_SIGNALS:
        if phrase in text:
            return {
                "is_job_email": False,
                "stage": "filtered",
                "reason": f"consulting_admin:{phrase}",
            }

    for phrase in NEGATIVE_KEYWORDS:
        if phrase in text:
            return {
                "is_job_email": False,
                "stage": "filtered",
                "reason": f"negative_signal:{phrase}",
            }

    for phrase in APPLICATION_SIGNALS:
        if phrase in text:
            return {
                "is_job_email": True,
                "stage": "candidate",
                "reason": f"application_signal:{phrase}",
            }

    for keyword in JOB_KEYWORDS:
        if keyword in text:
            return {
                "is_job_email": True,
                "stage": "candidate",
                "reason": f"job_keyword:{keyword}",
            }

    return {
        "is_job_email": False,
        "stage": "filtered",
        "reason": "no_job_signal",
    }


def is_job_email(email):
    return classify_job_email(email)["is_job_email"]
