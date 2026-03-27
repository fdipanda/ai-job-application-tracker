from pydantic import BaseModel, Field
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
    class Config:
        extra = "forbid"


class ApplicationUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    application_link: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        extra = "forbid"


class Application(ApplicationBase):
    email_subject: Optional[str] = None
    sender_email: Optional[str] = None
    email_received_at: Optional[datetime] = None

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
    audit_log_path: Optional[str] = None
    run_id: Optional[str] = None


class BacklogProcessRequest(BaseModel):
    max_pages: int = Field(default=20, ge=1, le=100)


class BacklogJobStartResponse(BaseModel):
    job_id: str
    status: str
    max_pages: int


class BacklogJobStatus(BaseModel):
    job_id: str
    status: str
    max_pages: int
    pages_processed: int
    emails_scanned: int
    applications_processed: int
    write_failures: int
    percent_complete: int
    elapsed_seconds: float
    eta_seconds: Optional[int] = None
    run_id: Optional[str] = None
    audit_log_path: Optional[str] = None
    error_message: Optional[str] = None
