from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuthState

OUTLOOK_PROVIDER = "outlook"


def get_access_token(db: Session, provider: str = OUTLOOK_PROVIDER) -> Optional[str]:
    auth_state = db.query(AuthState).filter(AuthState.provider == provider).first()
    if not auth_state:
        return None

    return auth_state.access_token


def save_access_token(db: Session, access_token: str, provider: str = OUTLOOK_PROVIDER) -> AuthState:
    auth_state = db.query(AuthState).filter(AuthState.provider == provider).first()

    if not auth_state:
        auth_state = AuthState(provider=provider)
        db.add(auth_state)

    auth_state.access_token = access_token
    auth_state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(auth_state)
    return auth_state
