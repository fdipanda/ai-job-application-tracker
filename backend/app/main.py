from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from . import models
from .routes import router
from app.services.email_service import fetch_recent_emails
from fastapi.responses import RedirectResponse
from app.services.outlook_auth import get_auth_url
from fastapi import Request
from app.services.outlook_auth import acquire_token_by_code
from app.services.email_service import process_backlog_emails

Base.metadata.create_all(bind=engine)

app = FastAPI()
ACCESS_TOKEN = None

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

    if ACCESS_TOKEN is None:
        return {"error": "Not authenticated"}

    print("TOKEN USED:", ACCESS_TOKEN[:50])

    return fetch_recent_emails(ACCESS_TOKEN)

@app.get("/auth/login")
def login():
    url = get_auth_url()
    return RedirectResponse(url)

import requests

@app.get("/auth/callback")
def auth_callback(request: Request):

    global ACCESS_TOKEN

    code = request.query_params.get("code")

    token_response = acquire_token_by_code(code)

    ACCESS_TOKEN = token_response["access_token"]

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

    if ACCESS_TOKEN is None:
        return {"error": "Not authenticated"}

    result = process_backlog_emails(ACCESS_TOKEN)

    return result