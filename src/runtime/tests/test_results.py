"""Results router: upload + auto-mark linked task done."""

from src.repo import models


def test_upload_marks_task_done(client, auth_headers, db_session):
    r = client.post(
        "/api/tasks", headers=auth_headers,
        json={"job_type": "hello_world", "urls": ["u"]},
    )
    tid = r.json()["ids"][0]

    r2 = client.post(
        "/api/results", headers=auth_headers,
        json={
            "task_id": tid, "url": "u", "total": 1,
            "data": {"message": "Hello, world!"},
        },
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    db_session.expire_all()
    task = db_session.get(models.Task, tid)
    assert task.status == "done"


def test_upload_without_task_id(client, auth_headers, db_session):
    r = client.post(
        "/api/results", headers=auth_headers,
        json={"url": "u", "total": 0, "data": {}},
    )
    assert r.status_code == 200
    rid = r.json()["result_id"]

    row = db_session.get(models.Result, rid)
    assert row is not None
    assert row.task_id is None


def test_upload_persists_client_id_from_request(client, auth_headers, db_session):
    """When client_id is in the request body, it's stored on the Result row."""
    r = client.post(
        "/api/results", headers=auth_headers,
        json={"url": "u", "total": 0, "data": {}, "client_id": "client_abc"},
    )
    rid = r.json()["result_id"]
    assert db_session.get(models.Result, rid).client_id == "client_abc"


def test_upload_falls_back_to_task_client_id(client, auth_headers, db_session):
    """If client_id is omitted but the linked task has one, copy it onto the Result."""
    r = client.post("/api/tasks", headers=auth_headers, json={
        "job_type": "hello_world", "urls": ["u"], "client_id": "owner_xyz",
    })
    tid = r.json()["ids"][0]

    r2 = client.post(
        "/api/results", headers=auth_headers,
        json={"task_id": tid, "url": "u", "total": 0, "data": {}},
    )
    rid = r2.json()["result_id"]
    assert db_session.get(models.Result, rid).client_id == "owner_xyz"
