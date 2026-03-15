import requests
from .email_parser import parse_email
from app.services.application_service import upsert_application
from app.database import SessionLocal
from app.services.ai_email_parser import parse_email_with_ai
from app.services.application_service import upsert_application
from .job_detector import is_job_email
import json
import os

GRAPH_API = "https://graph.microsoft.com/v1.0"


def fetch_recent_emails(access_token):

    db = SessionLocal()

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    url = "https://graph.microsoft.com/v1.0/me/messages?$select=subject,bodyPreview,body,from,receivedDateTime&$orderby=receivedDateTime desc&$top=50"

    emails = []


    while url:
        response = requests.get(url, headers=headers)
        data = response.json()

        for m in data["value"]:
            email = {
            "subject": m["subject"],
            "preview": m["bodyPreview"],
            "body": m["body"]["content"],
            "sender": m["from"]["emailAddress"]["address"],
            "received": m["receivedDateTime"],
            "id": m["id"]
            }


            if not is_job_email(email):
                 continue

            parsed = parse_email_with_ai(email)

            if not parsed:
                parsed = parse_email(email)

            if parsed:
                upsert_application(db, parsed)
                emails.append({
                    **email,
                    **parsed
                })

        url = data.get("@odata.nextLink")

    db.commit()
    db.close()

    return emails

def process_backlog_emails(access_token, max_pages=20):

    db = SessionLocal()

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    url = "https://graph.microsoft.com/v1.0/me/messages?$select=subject,bodyPreview,body,from,receivedDateTime,id&$orderby=receivedDateTime desc&$top=50"

    pages_processed = 0
    processed_count = 0

    while url and pages_processed < max_pages:

        print(f"Processing page {pages_processed + 1}")

        response = requests.get(url, headers=headers)
        data = response.json()

        for m in data["value"]:

            email = {
                "subject": m["subject"],
                "preview": m["bodyPreview"],
                "body": m["body"]["content"],
                "sender": m["from"]["emailAddress"]["address"],
                "received": m["receivedDateTime"],
                "id": m["id"]
            }

            # filter non-job emails
            if not is_job_email(email):
                continue

            parsed = parse_email_with_ai(email)

            if not parsed:
                parsed = parse_email(email)

            # DEBUG LOG
            log_path = os.path.join(os.getcwd(), "email_debug.json")

            with open(log_path, "a") as f:
                log_entry = {
                    "email_id": email["id"],
                    "received": email["received"],
                    "subject": email["subject"],
                    "sender": email["sender"],
                    "parsed": parsed
                }
                f.write(json.dumps(log_entry, indent=2))
                f.write("\n\n")

            if parsed and parsed.get("company") and parsed.get("role"):
                upsert_application(db, parsed)
                processed_count += 1

                print(f"Applications detected so far: {processed_count}")


        url = data.get("@odata.nextLink")
        pages_processed += 1
        db.commit()

        print(f"Finished page {pages_processed}")

    db.commit()
    db.close()

    return {
        "pages_processed": pages_processed,
        "applications_processed": processed_count
    }