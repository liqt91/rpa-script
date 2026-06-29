"""Clients router: register + heartbeat."""

from src.repo import models


def test_register(client, auth_headers, db_session):
    r = client.post(
        "/api/clients/register", headers=auth_headers,
        json={"hostname": "host1", "ip": "1.2.3.4", "os": "Win10"},
    )
    assert r.status_code == 200
    cid = r.json()["client_id"]
    assert len(cid) == 12

    row = db_session.get(models.Client, cid)
    assert row is not None
    assert row.hostname == "host1"


def test_heartbeat_creates_new(client, auth_headers, db_session):
    r = client.post(
        "/api/clients/heartbeat", headers=auth_headers,
        json={"client_id": "newclient", "status": "idle", "version": "0.1.0"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert db_session.get(models.Client, "newclient") is not None


def test_heartbeat_updates_existing(client, auth_headers, db_session):
    cid = client.post(
        "/api/clients/register", headers=auth_headers,
        json={"hostname": "h", "ip": "1.1.1.1", "os": "Win"},
    ).json()["client_id"]

    r = client.post(
        "/api/clients/heartbeat", headers=auth_headers,
        json={"client_id": cid, "status": "busy", "version": "0.2.0"},
    )
    assert r.status_code == 200

    db_session.expire_all()
    row = db_session.get(models.Client, cid)
    assert row.status == "busy"
    assert row.version == "0.2.0"


def test_heartbeat_returns_push_tasks(client, auth_headers):
    client.post(
        "/api/tasks", headers=auth_headers,
        json={"job_type": "hello_world", "urls": ["u"], "client_id": "client_x"},
    )
    r = client.post(
        "/api/clients/heartbeat", headers=auth_headers,
        json={"client_id": "client_x", "status": "idle"},
    )
    push = r.json()["push_tasks"]
    assert len(push) == 1
    assert push[0]["job_type"] == "hello_world"
