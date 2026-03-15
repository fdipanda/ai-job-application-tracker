from openai import OpenAI
from dotenv import load_dotenv
import os
import json

from .email_classifier import COMMON_ATS_DOMAINS
from .email_classifier import classify_email

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def parse_email_with_ai(email):

    sender = email["sender"]

    # extract sender domain
    domain = sender.split("@")[-1].split(".")[0]

    is_ats = domain.lower() in COMMON_ATS_DOMAINS

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

        result = response.output_text

        parsed = json.loads(result)

        # safety check: if ATS mistakenly used as company
        if parsed.get("company", "").lower() in COMMON_ATS_DOMAINS:
            parsed["company"] = None

        company = parsed.get("company","").lower()

        email_text = (email["subject"] + email["body"]).lower()

        if company and company not in email_text:
            return None
        
        # email classification
        status = classify_email(email)

        if status == "Unknown":
            status = "Applied"

        parsed["status"] = status
   

        return parsed

    except Exception:
        return None