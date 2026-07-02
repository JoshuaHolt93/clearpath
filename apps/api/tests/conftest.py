from __future__ import annotations

import os
from collections.abc import Generator

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("CLEARPATH_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MFA_REQUIRED", "true")
os.environ.setdefault("EXPOSE_DEV_TOKENS", "true")
# Use a cheap KDF in tests. The strong scrypt default (~1s/hash) otherwise
# dominates the suite because MFA setup hashes 10 recovery codes per account.
os.environ.setdefault("PASSWORD_HASH_METHOD", "pbkdf2:sha256:1000")
os.environ.setdefault("CUSTOMER_DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("PLAID_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

from app.core.database import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


import pytest  # noqa: E402


@pytest.fixture
def db() -> Generator[Session, None, None]:
    reset_database()
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    reset_database()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()
        engine.dispose()
