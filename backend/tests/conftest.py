"""
Shared pytest fixtures.

Uses an in-memory SQLite database per test session (via StaticPool so the
single in-memory connection is reused across threads/requests) instead of
the dev SQLite file or a real Postgres instance, so tests never touch real
data and can run in CI with zero external services.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app.main import app
from app.db.session import Base, get_db
from app.db import models  # noqa: F401 ensures models are registered on Base

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin_token(db_session):
    """Creates a SuperAdmin user directly in the DB and mints a real access
    token for it — a legitimate shortcut for testing role-gated endpoints
    without re-exercising the full email+password+2FA login flow every time."""
    from app.db.models import User
    from app.core.security import create_access_token

    user = User(phone="+254700009999", name="Test Admin", role="SuperAdmin", status="Active")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return create_access_token(user.id, user.role)


@pytest.fixture()
def seeded_grid(db_session):
    """Inserts a single grid cell so prediction endpoints have something to query."""
    from app.db.models import GridCell

    cell = GridCell(village_name="TestVille", district="Test", country="Testland", lat=1.0, lon=40.0)
    db_session.add(cell)
    db_session.commit()
    db_session.refresh(cell)
    return cell
