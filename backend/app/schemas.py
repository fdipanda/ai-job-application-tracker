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