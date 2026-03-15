import json

import pytest

from app.services import ai_email_parser
from app.services import email_service
from app.services.email_parser import parse_email
from app.services.job_detector import classify_job_email


def test_ai_parser_invalid_json(monkeypatch):
    class Resp:
        output_text = "not a json"

    def fake_create(*args, **kwargs):
        return Resp()

    monkeypatch.setattr(ai_email_parser.client.responses, "create", fake_create)

    parsed, failure = ai_email_parser.parse_email_with_ai_result({"subject": "s", "preview": "p", "body": "b", "sender": "me@acme.com"})

    assert parsed is None
    assert failure["reason"] == "invalid_json"
    assert failure["raw_output"] == "not a json"


def test_ai_parser_raises_exception(monkeypatch):
    def fake_create(*args, **kwargs):
        raise RuntimeError("api down")

    monkeypatch.setattr(ai_email_parser.client.responses, "create", fake_create)

    parsed, failure = ai_email_parser.parse_email_with_ai_result({"subject": "s", "preview": "p", "body": "b", "sender": "me@acme.com"})

    assert parsed is None
    assert failure["reason"] == "RuntimeError"
    assert failure["raw_output"] is None


def test_regex_fallback_returns_parsed(monkeypatch):
    # Force AI parser to fail, so email_service falls back to regex parser
    monkeypatch.setattr(
        email_service,
        "parse_email_with_ai_result",
        lambda email: (None, {"reason": "invalid_json", "raw_output": "not json"}),
    )

    message = {
        "subject": "Interview for Backend Engineer at Acme",
        "bodyPreview": "preview",
        "body": {"content": "We would like to invite you for the Backend Engineer position at Acme in New York."},
        "from": {"emailAddress": {"address": "jobs@acme.com"}},
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "id": "1",
    }

    parsed, details = email_service._parse_job_email({
        "subject": message["subject"],
        "preview": message["bodyPreview"],
        "body": message["body"]["content"],
        "sender": message["from"]["emailAddress"]["address"],
        "received": message["receivedDateTime"],
        "id": message["id"],
    })

    assert parsed is not None
    assert details["parser"] == "regex"
    assert details["ai_failure_reason"] == "invalid_json"
    assert details["raw_ai_output"] == "not json"
    assert "Acme" in parsed.get("company", "") or parsed.get("company") is not None


def test_ai_parser_extracts_json_from_code_fence(monkeypatch):
    class Resp:
        output_text = '```json\n{"company":"Acme","role":"Backend Engineer","location":"Remote","status":"Applied"}\n```'

    monkeypatch.setattr(ai_email_parser.client.responses, "create", lambda *args, **kwargs: Resp())

    parsed, failure = ai_email_parser.parse_email_with_ai_result(
        {"subject": "s", "preview": "p", "body": "Backend Engineer at Acme", "sender": "me@acme.com"}
    )

    assert failure is None
    assert parsed["company"] == "Acme"


def test_job_detector_filters_timesheet_admin_mail():
    email = {
        "subject": "Your Timesheet for Commonwealth GBV SRHR Received",
        "preview": "Week Ending 2026-03-07",
        "body": "Your timesheet for Week Ending 2026-03-07 has been received.",
        "sender": "admin@consulting.example.com",
    }

    result = classify_job_email(email)

    assert result["is_job_email"] is False
    assert result["reason"].startswith("consulting_admin:")


def test_regex_parser_trims_generic_company_fragments():
    parsed = parse_email(
        {
            "subject": "Thank you for your online submission",
            "preview": "Hello Franck",
            "body": (
                "Thank you for your online submission for the Software Engineer position "
                "at Hewlett Packard Enterprise Careers."
            ),
            "sender": "jobs@hpe.com",
        }
    )

    assert parsed["company"] == "Hewlett Packard Enterprise"
