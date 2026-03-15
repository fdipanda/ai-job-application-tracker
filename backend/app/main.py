from threading import Lock

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import models, schemas
from .database import Base, SessionLocal, engine
from .routes import router
from app.services.auth_state_service import get_access_token, save_access_token
from app.services.email_service import (
    fetch_recent_emails,
    process_backlog_emails,
    process_new_emails,
)
from app.services.outlook_auth import acquire_token_by_code, get_auth_url

Base.metadata.create_all(bind=engine)

app = FastAPI()
ACCESS_TOKEN = None
EMAIL_SYNC_LOCK = Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

    print("TOKEN USED:", access_token[:50])
    return fetch_recent_emails(access_token)


@app.get("/auth/login")
def login():
    url = get_auth_url()
    return RedirectResponse(url)


@app.get("/auth/callback")
def auth_callback(request: Request):
    global ACCESS_TOKEN

    code = request.query_params.get("code")
    token_response = acquire_token_by_code(code)
    ACCESS_TOKEN = token_response["access_token"]

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

    return {"message": "Login successful"}


@app.get("/process-backlog")
def run_backlog():
    access_token = _require_access_token()
    _acquire_email_lock()

    try:
        return process_backlog_emails(access_token)
    finally:
        EMAIL_SYNC_LOCK.release()


@app.post("/emails/sync-new", response_model=schemas.EmailSyncSummary)
def sync_new_emails():
    access_token = _require_access_token()
    _acquire_email_lock()

    try:
        return process_new_emails(access_token)
    finally:
        EMAIL_SYNC_LOCK.release()


def _require_access_token():
    global ACCESS_TOKEN

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
    if not EMAIL_SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Email sync already in progress")
