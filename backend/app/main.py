import os
from threading import Lock

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import models, schemas
from .database import Base, SessionLocal, engine, ensure_sqlite_schema
from .routes import router
from app.services.auth_state_service import clear_access_token, get_access_token, save_access_token
from app.services.backlog_job_service import BacklogJobStore
from app.services.email_service import (
    GraphAuthenticationError,
    fetch_recent_emails,
    process_backlog_emails,
    process_new_emails,
)
from app.services.outlook_auth import acquire_token_by_code, get_auth_url

Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI()
ACCESS_TOKEN = None
EMAIL_SYNC_LOCK = Lock()
# This store acts like a tiny in-memory job manager for long-running backlog scans.
# In C# terms, think of it as a singleton service holding background job state.
BACKLOG_JOB_STORE = BacklogJobStore()
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {"message": "AI Job Application Tracker API is running"}


@app.get("/emails")
def get_emails():
    access_token = _require_access_token()

    try:
        print("TOKEN USED:", access_token[:50])
        return fetch_recent_emails(access_token)
    except GraphAuthenticationError:
        _clear_outlook_auth_state()
        raise HTTPException(status_code=401, detail="Outlook session expired. Please reconnect.")


@app.get("/auth/login")
def login():
    url = get_auth_url()
    return RedirectResponse(url)


@app.get("/auth/callback")
def auth_callback(request: Request):
    global ACCESS_TOKEN

    # Microsoft redirects the user back here with a temporary auth code.
    # The backend exchanges that code for an access token and then redirects
    # the browser back to the frontend with a success/failure flag.
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(f"{FRONTEND_URL}?outlook=error", status_code=302)

    token_response = acquire_token_by_code(code)
    access_token = token_response.get("access_token")
    if not access_token:
        return RedirectResponse(f"{FRONTEND_URL}?outlook=error", status_code=302)

    ACCESS_TOKEN = access_token

    db = SessionLocal()
    try:
        save_access_token(db, ACCESS_TOKEN)
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    test = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers=headers
    )

    print("GRAPH TEST STATUS:", test.status_code)
    print("GRAPH TEST RESPONSE:", test.text[:200])

    return RedirectResponse(f"{FRONTEND_URL}?outlook=connected", status_code=302)


@app.get("/auth/status")
def auth_status():
    global ACCESS_TOKEN

    # First check in-memory state, then fall back to the persisted token.
    # This is similar to checking a cached auth/session value before reading from storage.
    if ACCESS_TOKEN is not None:
        return {"authenticated": True}

    db = SessionLocal()
    try:
        stored_token = get_access_token(db)
    finally:
        db.close()

    return {"authenticated": stored_token is not None}


@app.get("/process-backlog")
def run_backlog():
    access_token = _require_access_token()
    _acquire_email_lock()

    try:
        return process_backlog_emails(access_token)
    except GraphAuthenticationError:
        _clear_outlook_auth_state()
        raise HTTPException(status_code=401, detail="Outlook session expired. Please reconnect.")
    finally:
        EMAIL_SYNC_LOCK.release()


@app.post("/emails/process-backlog", response_model=schemas.BacklogJobStartResponse)
def start_backlog_job(payload: schemas.BacklogProcessRequest):
    access_token = _require_access_token()
    _acquire_email_lock()

    try:
        # The runner is injected here so the job store stays generic and does not
        # need to know how email processing itself works.
        job = BACKLOG_JOB_STORE.start_job(
            max_pages=payload.max_pages,
            access_token=access_token,
            runner=process_backlog_emails,
            release_sync_lock=EMAIL_SYNC_LOCK.release,
        )
    except Exception:
        EMAIL_SYNC_LOCK.release()
        raise

    return {
        "job_id": job.job_id,
        "status": job.status,
        "max_pages": job.max_pages,
    }


@app.get("/emails/process-backlog/{job_id}", response_model=schemas.BacklogJobStatus)
def get_backlog_job_status(job_id: str):
    job = BACKLOG_JOB_STORE.get_job(job_id)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "max_pages": job.max_pages,
        "pages_processed": job.pages_processed,
        "emails_scanned": job.emails_scanned,
        "applications_processed": job.applications_processed,
        "write_failures": job.write_failures,
        "percent_complete": job.percent_complete,
        "elapsed_seconds": job.elapsed_seconds,
        "eta_seconds": job.eta_seconds,
        "run_id": job.run_id,
        "audit_log_path": job.audit_log_path,
        "error_message": job.error_message,
    }


@app.post("/emails/sync-new", response_model=schemas.EmailSyncSummary)
def sync_new_emails():
    access_token = _require_access_token()
    _acquire_email_lock()

    try:
        return process_new_emails(access_token)
    except GraphAuthenticationError:
        _clear_outlook_auth_state()
        raise HTTPException(status_code=401, detail="Outlook session expired. Please reconnect.")
    finally:
        EMAIL_SYNC_LOCK.release()


def _require_access_token():
    global ACCESS_TOKEN

    # This helper centralizes "am I authenticated?" checks so every email endpoint
    # does not have to duplicate the same token-loading logic.
    if ACCESS_TOKEN is not None:
        return ACCESS_TOKEN

    db = SessionLocal()
    try:
        ACCESS_TOKEN = get_access_token(db)
    finally:
        db.close()

    if ACCESS_TOKEN is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return ACCESS_TOKEN


def _acquire_email_lock():
    # Only allow one email sync/backlog job at a time.
    # SQLite and the email pipeline are simpler to reason about when these are serialized.
    if not EMAIL_SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Email sync already in progress")


def _clear_outlook_auth_state():
    global ACCESS_TOKEN

    ACCESS_TOKEN = None
    db = SessionLocal()
    try:
        clear_access_token(db)
    finally:
        db.close()
