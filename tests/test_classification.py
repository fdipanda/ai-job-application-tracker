from app.services.email_classifier import classify_email


def test_classify_assessment():
    email = {"subject": "Please complete this assessment", "body": "We have a coding challenge for you"}
    assert classify_email(email) == "Assessment"


def test_classify_recruiter_contact():
    email = {"subject": "Introductory call", "body": "A recruiter would love to connect"}
    assert classify_email(email) == "Recruiter Contact"


def test_classify_final_interview():
    email = {"subject": "Final Interview Scheduled", "body": "This is the final interview with the hiring manager"}
    assert classify_email(email) == "Final Interview"


def test_classify_withdrawn():
    email = {"subject": "You withdrew your application", "body": "The application withdrawn message"}
    assert classify_email(email) == "Withdrawn"


def test_classify_rejection_overrides_prior_pipeline_signals():
    email = {
        "subject": "Interview update",
        "body": "After careful consideration, we are not moving forward after your final interview.",
    }

    assert classify_email(email) == "Rejected"
