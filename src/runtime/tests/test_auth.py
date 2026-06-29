"""Auth router: login flow + protected-endpoint behavior."""

from src.repo import runtime_models as models
from src.runtime import auth

def test_login_ok(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 20


def test_login_wrong_password(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "x"},
    )
    assert r.status_code == 401


def test_protected_endpoint_no_header(client):
    r = client.get("/api/tasks/pending", params={"client_id": "x"})
    assert r.status_code == 401


def test_protected_endpoint_bad_token(client):
    r = client.get(
        "/api/tasks/pending",
        params={"client_id": "x"},
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 401


def test_change_password_ok(client, auth_headers, db_session):
    r = client.post(
        "/api/auth/password",
        headers=auth_headers,
        json={"old_password": "admin123", "new_password": "newpass123"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # Login with new password works.
    r2 = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "newpass123"},
    )
    assert r2.status_code == 200

    # Revert so session-scoped fixtures stay valid.
    admin = db_session.query(models.User).filter(models.User.username == "admin").first()
    admin.hashed_password = auth.hash_password("admin123")
    db_session.commit()


def test_change_password_wrong_old(client, auth_headers):
    r = client.post(
        "/api/auth/password",
        headers=auth_headers,
        json={"old_password": "wrong", "new_password": "newpass123"},
    )
    assert r.status_code == 400
    assert "原密码" in r.json()["detail"]


def test_change_password_too_short(client, auth_headers):
    r = client.post(
        "/api/auth/password",
        headers=auth_headers,
        json={"old_password": "admin123", "new_password": "12345"},
    )
    assert r.status_code == 400
    assert "长度" in r.json()["detail"]
