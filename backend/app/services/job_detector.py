import email


JOB_KEYWORDS = [
    "application",
    "interview",
    "assessment",
    "coding challenge",
    "recruiter",
    "career",
    "talent",
    "position",
    "thank you for applying"
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
    "promotion"
]

BLOCKED_SENDERS = [
    "linkedin.com",
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "notifications@ripplematch.com",
    "glassdoor.com",
    "indeed.com"
]

APPLICATION_SIGNALS = [
    "application received",
    "thanks for applying",
    "thank you for applying",
    "your application",
    "we received your application",
    "confirm that your application",
]

def is_job_email(email):
    


    sender = email.get("sender", "").lower()

    # 1️⃣ Block known job newsletters
    for blocked in BLOCKED_SENDERS:
        if blocked in sender:
            return False


    text = (
        email.get("subject","") +
        email.get("preview","") +
        email.get("body","")
    ).lower()


    # 2️⃣ Negative signals
    for phrase in NEGATIVE_KEYWORDS:
        if phrase in text:
            return False


    # 3️⃣ Strong application signals
    for phrase in APPLICATION_SIGNALS:
        if phrase in text:
            return True


    # 4️⃣ Weak signals (job keywords)
    for keyword in JOB_KEYWORDS:
        if keyword in text:
            return True


    return False