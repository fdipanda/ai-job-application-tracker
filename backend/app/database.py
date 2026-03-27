from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BACKEND_DIR / "applications.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _connection_record):
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout = 30000")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
    finally:
        cursor.close()


def ensure_sqlite_schema() -> None:
    with engine.begin() as connection:
        table_names = {
            row[0]
            for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        if "applications" not in table_names:
            return

        existing_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(applications)"))
        }
        migrations = {
            "email_subject": "ALTER TABLE applications ADD COLUMN email_subject VARCHAR",
            "sender_email": "ALTER TABLE applications ADD COLUMN sender_email VARCHAR",
            "email_received_at": "ALTER TABLE applications ADD COLUMN email_received_at DATETIME",
        }

        for column_name, statement in migrations.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))
