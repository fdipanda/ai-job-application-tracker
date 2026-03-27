import os
import sys
import pytest

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker


# Ensure backend 'app' package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from app.database import Base


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session(engine):
    SessionTesting = sessionmaker(bind=engine)
    session = SessionTesting()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    # Import here so app uses our modified sys.path
    from fastapi.testclient import TestClient
    import app.main as main
    import app.routes as routes
    from app.services.backlog_job_service import BacklogJobStore

    # override DB dependency used by routes.get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    main.app.dependency_overrides[routes.get_db] = override_get_db

    # ensure tables exist on the test session's bind
    Base.metadata.create_all(bind=db_session.bind)
    main.ACCESS_TOKEN = None
    main.BACKLOG_JOB_STORE = BacklogJobStore()
    # Keep auth-related tests isolated from any real local SQLite auth state.
    # Individual tests can still monkeypatch this if they need a different behavior.
    main.get_access_token = lambda db: None
    if main.EMAIL_SYNC_LOCK.locked():
        main.EMAIL_SYNC_LOCK.release()

    return TestClient(main.app)
