"""
Pytest fixtures for the server.

DATABASE_URL is set at module import time, BEFORE any `from server` import,
so models.engine and the lifespan handler both bind to a temp SQLite file
rather than the production server/data.db.
"""

import os
import tempfile
from pathlib import Path

_DB_DIR = Path(tempfile.mkdtemp(prefix="xhs_test_"))
_DB_PATH = _DB_DIR / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"

import pytest
from fastapi.testclient import TestClient

from src.runtime.main import app as _app
from src.repo import models


@pytest.fixture(scope="session")
def app():
    return _app


@pytest.fixture(scope="session")
def client(app):
    """Session-scope TestClient. The context manager triggers lifespan, which
    seeds the default admin/admin123 user into the test DB."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    """Truncate mutable tables before each test. Keep `users` (admin) intact."""
    models.init_db()
    db = models.SessionLocal()
    try:
        db.query(models.Result).delete()
        db.query(models.Task).delete()
        db.query(models.Client).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def db_session():
    s = models.SessionLocal()
    try:
        yield s
    finally:
        s.close()
