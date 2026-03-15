import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from .email_classifier import COMMON_ATS_DOMAINS
from .email_classifier import classify_email

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)


def parse_email_with_ai(email):
    parsed_email, _ = parse_email_with_ai_result(email)
    return parsed_email


def parse_email_with_ai_result(email):
    sender = email["sender"]
    domain = sender.split("@")[-1].split(".")[0]

    content = f"""
Subject: {email["subject"]}
Preview: {email["preview"]}
From: {sender}
Body: {email["body"][:2000]}
"""

    prompt = f"""
Extract job application information from this email.

Sender domain: {domain}

If the sender domain belongs to an Applicant Tracking System (ATS)
like Greenhouse, Lever, Workday, iCIMS, or SmartRecruiters,
DO NOT use that domain as the company name.

Instead identify the company mentioned in the email text.

Return ONLY valid JSON:

{{
"company": "",
"role": "",
"location": "",
"status": ""
}}

Email:
{content}
"""

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        raw_output = response.output_text or ""
        parsed = json.loads(_extract_json_payload(raw_output))

        if parsed.get("company", "").lower() in COMMON_ATS_DOMAINS:
            parsed["company"] = None

        company = parsed.get("company", "").lower()
        email_text = (email["subject"] + email["body"]).lower()

        if company and company not in email_text:
            logger.warning(
                "Discarding AI parse for email %s because company %r was not found in the email body",
                email.get("id", "unknown"),
                company,
            )
            return None, {
                "reason": "company_not_in_email",
                "raw_output": _truncate_raw_output(raw_output),
            }

        status = classify_email(email)
        if status == "Unknown":
            status = "Applied"

        parsed["status"] = status
        return parsed, None
    except json.JSONDecodeError as exc:
        logger.warning(
            "AI parser returned invalid JSON for email %s: %s",
            email.get("id", "unknown"),
            exc,
        )
        return None, {
            "reason": "invalid_json",
            "raw_output": _truncate_raw_output(locals().get("raw_output", "")),
        }
    except Exception as exc:
        logger.exception(
            "AI parser failed for email %s",
            email.get("id", "unknown"),
        )
        return None, {
            "reason": exc.__class__.__name__,
            "raw_output": None,
        }


def _extract_json_payload(raw_output):
    cleaned = raw_output.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    start_index = cleaned.find("{")
    end_index = cleaned.rfind("}")

    if start_index != -1 and end_index != -1 and end_index >= start_index:
        return cleaned[start_index:end_index + 1]

    return cleaned


def _truncate_raw_output(raw_output):
    if not raw_output:
        return None

    cleaned = raw_output.strip()
    if len(cleaned) <= 500:
        return cleaned

    return cleaned[:500]
