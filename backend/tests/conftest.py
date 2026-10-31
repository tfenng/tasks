from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "TASK_CONTROL_DATABASE_URL", "postgresql+psycopg://localhost:5432/task_control_test"
)
os.environ.setdefault("TASK_CONTROL_SCRIPT_ROOT", tempfile.mkdtemp(prefix="tc-scripts-"))
os.environ.setdefault("TASK_CONTROL_COOKIE_SECURE", "false")
os.environ.setdefault(
    "TASK_CONTROL_SECRET_KEYS",
    '{"1":"ZGV2LW9ubHktMzItYnl0ZS1rZXktZm9yLXRlc3RzISE="}',
)

import pytest
from fastapi.testclient import TestClient

from task_control.api.rate_limit import limiter
from task_control.infrastructure.db.models import Base, User
from task_control.infrastructure.db.session import SessionLocal, engine
from task_control.infrastructure.security.passwords import hash_password


@pytest.fixture(autouse=True)
def clean_database():
    limiter.reset()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    from task_control.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin():
    with SessionLocal() as db:
        user = User(
            username="admin",
            display_name="Admin",
            password_hash=hash_password("adminpassword123"),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def logged_in_client(client, admin):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "adminpassword123"},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.headers["X-CSRF-Token"] = csrf
    return client
