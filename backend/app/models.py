from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    company: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)

    job_key: Mapped[str] = mapped_column(String, index=True)
    location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    application_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    date_applied: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)