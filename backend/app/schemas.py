from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ApplicationBase(BaseModel):
    company: str
    role: str
    status: str
    location: Optional[str] = None
    application_link: Optional[str] = None
    notes: Optional[str] = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    application_link: Optional[str] = None
    notes: Optional[str] = None


class Application(ApplicationBase):
    id: int
    date_applied: datetime
    last_updated: datetime

    class Config:
        orm_mode = True


class EmailSyncSummary(BaseModel):
    scanned_count: int
    detected_count: int
    added_count: int
    updated_count: int
    skipped_count: int
    write_failures: int
    checkpoint_at: Optional[datetime] = None
    last_run_status: str
