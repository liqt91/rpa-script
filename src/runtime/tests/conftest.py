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
os.environ["SECRET_KEY"] = os.environ.get("SECRET_KEY", "test-secret-key-for-pytest-only")

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
    seeds the default admin/admin123 user into the test DB.

    base_url 用 http://localhost：main.py 的 host_guard 中间件只放行本机 host，
    TestClient 默认 host 是 testserver 会被拒（forbidden host）。
    """
    with TestClient(app, base_url="http://localhost") as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    """Truncate mutable tables before each test. Keep `users` (admin) intact.

    按外键依赖顺序清（先子后父），并覆盖 Workflow 体系——这些表被 workflow/命令/
    数据表格等测试写入，不清会跨测试污染计数（如 test_dashboard_stats 的 workflow_count）。
    """
    models.init_db()
    db = models.SessionLocal()
    try:
        db.query(models.WorkflowNode).delete()
        db.query(models.WorkflowElement).delete()
        db.query(models.WorkflowCommand).delete()
        db.query(models.DataTable).delete()
        db.query(models.CommandCategory).delete()
        db.query(models.Workflow).delete()
        db.query(models.Result).delete()
        db.query(models.Task).delete()
        db.query(models.Client).delete()
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def admin_token():
    """免登录（认证已移除，见 auth.py）：不再有 /api/auth/login。
    返回占位 token 以满足依赖 auth_headers 的测试签名（实际请求无需有效 token）。"""
    return "no-auth"


@pytest.fixture
def auth_headers(admin_token):
    """免登录：get_current_user 恒放行为 admin，业务 API 无需 Authorization。
    保留空头以满足旧测试签名（传了也忽略）。"""
    return {}


@pytest.fixture
def db_session():
    s = models.SessionLocal()
    try:
        yield s
    finally:
        s.close()
