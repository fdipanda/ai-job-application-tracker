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

_msal_app = None


def get_msal_app():
    global _msal_app

    if _msal_app is None:
        _msal_app = ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET
        )

    return _msal_app


def get_auth_url():
    return get_msal_app().get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI
    )


def acquire_token_by_code(code):
    result = get_msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    return result
