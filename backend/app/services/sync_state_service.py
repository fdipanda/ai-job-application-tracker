from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import SyncState

NEW_EMAIL_SYNC_TYPE = "new_email_scan"


def get_sync_state(db: Session, sync_type: str = NEW_EMAIL_SYNC_TYPE) -> SyncState:
    sync_state = db.query(SyncState).filter(SyncState.sync_type == sync_type).first()

    if not sync_state:
        sync_state = SyncState(sync_type=sync_type)
        db.add(sync_state)
        db.commit()
        db.refresh(sync_state)

    return sync_state


def mark_sync_started(db: Session, sync_type: str = NEW_EMAIL_SYNC_TYPE) -> SyncState:
    sync_state = get_sync_state(db, sync_type)
    sync_state.last_run_at = datetime.utcnow()
    sync_state.last_run_status = "running"
    db.commit()
    db.refresh(sync_state)
    return sync_state


def mark_sync_finished(
    db: Session,
    status: str,
    checkpoint_at: Optional[datetime] = None,
    sync_type: str = NEW_EMAIL_SYNC_TYPE,
) -> SyncState:
    sync_state = get_sync_state(db, sync_type)
    sync_state.last_run_at = datetime.utcnow()
    sync_state.last_run_status = status

    if checkpoint_at is not None and status == "success":
        sync_state.last_email_received_at = checkpoint_at

    db.commit()
    db.refresh(sync_state)
    return sync_state
