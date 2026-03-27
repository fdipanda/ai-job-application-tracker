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


def test_rejection_wins_over_talent_acquisition_language():
    email = {
        "subject": "Update from Talent Acquisition",
        "body": (
            "Thank you for your interest. We have decided to pursue other candidates at this time. "
            "Please stay connected with our talent acquisition team for future opportunities."
        ),
    }

    assert classify_email(email) == "Rejected"


def test_confirmation_email_stays_applied():
    email = {
        "subject": "Thank you for your application",
        "body": (
            "We've received your application for the Backend Engineer role and are currently reviewing "
            "your application. Talent Acquisition will be in touch if there is a match."
        ),
    }

    assert classify_email(email) == "Applied"


def test_future_assessment_mention_does_not_count_as_assessment():
    email = {
        "subject": "Application received",
        "body": (
            "Thank you for applying. If selected, you may receive an assessment in the next step of the "
            "process."
        ),
    }

    assert classify_email(email) == "Applied"


def test_direct_coding_challenge_request_is_assessment():
    email = {
        "subject": "Complete your HackerRank assessment",
        "body": "Please use the link below to complete your coding challenge within 5 days.",
    }

    assert classify_email(email) == "Assessment"
