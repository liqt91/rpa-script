"""认证现状：认证/密码功能已移除（commit 66d8f83），后端为「本机免登录」。

- 不再有 /api/auth/login、/api/auth/password 路由。
- 依赖 get_current_user 的 API 由 _default_user 直接放行为 admin（免认证）。
- 本文件验证"认证移除后"的行为契约，不再测试 401/登录流。
"""

from src.repo import runtime_models as models
from src.runtime import auth


def test_login_endpoint_removed(client):
    """登录路由已移除（认证功能删除）→ 404 而非 200/401。"""
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 404


def test_password_endpoint_removed(client):
    """改密路由已移除 → 404。"""
    r = client.post(
        "/api/auth/password",
        json={"old_password": "admin123", "new_password": "x"},
    )
    assert r.status_code == 404


def test_protected_endpoint_no_header(client):
    """免登录：受保护端点无 Authorization 头也应可访问（get_current_user 放行）。"""
    r = client.get("/api/tasks/pending", params={"client_id": "x"})
    assert r.status_code == 200


def test_protected_endpoint_with_bad_token(client):
    """免登录：即便传无效 Bearer 也放行（忽略凭据）。"""
    r = client.get(
        "/api/tasks/pending",
        params={"client_id": "x"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 200


def test_default_user_from_db(client, db_session):
    """admin 种子行存在（lifespan 创建），_default_user 返回它。"""
    db = db_session
    user = db.query(models.User).filter(models.User.username == "admin").first()
    assert user is not None


def test_hash_password_roundtrip():
    """hash_password 保留（历史数据兼容），bcrypt 可校验。"""
    hashed = auth.hash_password("admin123")
    assert hashed.startswith("$2")
