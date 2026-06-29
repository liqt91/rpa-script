"""Admin API endpoints."""

from src.repo import runtime_models as models
from src.runtime import auth


def test_dashboard_stats(client, auth_headers, db_session):
    # Seed one task and one result so counts are non-zero.
    db_session.add(models.Task(job_type="hello_world", url="https://example.com", status="pending"))
    db_session.add(models.Result(url="https://example.com", total=1, data='{"x":1}'))
    db_session.commit()

    r = client.get("/api/admin/dashboard", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["tasks_total"] == 1
    assert body["tasks_pending"] == 1
    assert body["results_total"] == 1
    assert "clients_total" in body


def test_dashboard_requires_auth(client):
    assert client.get("/api/admin/dashboard").status_code == 401


def test_open_db_folder(client, auth_headers, monkeypatch):
    opened = {"path": None}

    def fake_startfile(path):
        opened["path"] = path

    monkeypatch.setattr("os.startfile", fake_startfile, raising=False)
    r = client.post("/api/system/open-db-folder", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["opened"] is True
    assert opened["path"] == body["path"]
