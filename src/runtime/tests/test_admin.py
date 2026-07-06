"""Admin API endpoints."""

from src.repo import runtime_models as models


def test_dashboard_stats(client, auth_headers, db_session):
    # Seed one workflow and one result so counts are non-zero.
    db_session.add(models.Workflow(name="test workflow", url="https://example.com"))
    db_session.add(models.Result(url="https://example.com", total=1, data='{"x":1}'))
    db_session.commit()

    r = client.get("/api/admin/dashboard", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["workflow_count"] == 1
    assert body["run_count"] == 1


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
