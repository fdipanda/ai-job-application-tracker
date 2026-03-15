import os
from msal import ConfidentialClientApplication
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
TENANT_ID = os.getenv("OUTLOOK_TENANT_ID")
REDIRECT_URI = os.getenv("OUTLOOK_REDIRECT_URI")

AUTHORITY = AUTHORITY = "https://login.microsoftonline.com/common"

SCOPES = [
    "User.Read",
    "Mail.Read"
]

app = ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential=CLIENT_SECRET
)


def get_auth_url():
    return app.get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI
    )


def acquire_token_by_code(code):
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    return result