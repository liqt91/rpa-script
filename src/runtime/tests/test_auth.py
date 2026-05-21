"""Auth router: login flow + protected-endpoint behavior."""


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
