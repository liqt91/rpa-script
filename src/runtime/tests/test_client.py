"""Client CLI: config + job discovery + e2e via TestClient injection.

The e2e tests inject the session-scope `TestClient` (an httpx.Client subclass
with starlette's sync ASGI transport) into ApiClient via its `session` kwarg.
That way the client code talks to the same FastAPI instance the rest of the
suite uses — no live socket, no httpx.ASGITransport (which is async-only in
httpx 0.28).
"""

from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import os

import pytest

import client as cli
from src.repo import models


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "client_config.json"
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg_path)
    return cfg_path


@pytest.fixture
def asgi_factory(client):
    """Wrap ApiClient around the session-scope TestClient (an httpx.Client subclass
    with starlette's sync ASGI transport)."""
    return lambda: cli.ApiClient(session=client)


# ===== config =====

def test_config_default_when_missing(tmp_config):
    cfg = cli.load_config()
    assert cfg["server"]["url"] == "http://localhost:8000"
    assert cfg["client"]["id"] == ""


def test_config_round_trip(tmp_config):
    cfg = cli.default_config()
    cfg["client"]["id"] = "abc123"
    cfg["token"] = "tok"
    cli.save_config(cfg)
    loaded = cli.load_config()
    assert loaded["client"]["id"] == "abc123"
    assert loaded["token"] == "tok"


# ===== job discovery =====

def test_discover_jobs_lists_xhs_comments():
    assert "xhs_comments" in cli.discover_jobs()


def test_load_run_unknown():
    with pytest.raises(ValueError):
        cli.load_run("does_not_exist_999")


# ===== e2e: setup =====

def test_cmd_setup_e2e(tmp_config, asgi_factory):
    args = SimpleNamespace(server="http://testserver", user=None, password=None)
    cid = cli.cmd_setup(args, client_factory=asgi_factory)
    assert len(cid) == 12

    cfg = cli.load_config()
    assert cfg["client"]["id"] == cid
    assert cfg["token"]
    # Server-side: client row exists.
    db = models.SessionLocal()
    try:
        assert db.get(models.Client, cid) is not None
    finally:
        db.close()


# ===== e2e: pull → execute → upload =====

def test_cmd_pull_executes_and_uploads(tmp_config, asgi_factory, client, auth_headers):
    """Full happy path: client pulls a task, runs it (mocked), uploads result.
    The pytest `client` fixture is the TestClient used to seed the task."""
    # 1. set up the client (logs in + registers)
    args = SimpleNamespace(server="http://testserver", user=None, password=None)
    cid = cli.cmd_setup(args, client_factory=asgi_factory)

    # 2. seed a task assigned to this client_id
    r = client.post(
        "/api/tasks", headers=auth_headers,
        json={
            "job_type": "xhs_comments",
            "urls": ["https://www.xiaohongshu.com/explore/fake"],
            "client_id": cid,
            "params": {"scrolls": 3, "delay": 0.1},
        },
    )
    task_id = r.json()["ids"][0]

    # 3. run cmd_pull, but mock execute_job (DrissionPage is not installed in venv)
    fake_result = {"total": 2, "items": [{"author": "a", "content": "x"}, {"author": "b"}]}
    with patch.object(cli, "execute_job", return_value=fake_result) as exec_mock:
        cli.cmd_pull(SimpleNamespace(), client_factory=asgi_factory)

    exec_mock.assert_called_once()
    job_type, url, params = exec_mock.call_args[0]
    assert job_type == "xhs_comments"
    assert url == "https://www.xiaohongshu.com/explore/fake"
    assert params == {"scrolls": 3, "delay": 0.1}

    # 4. server-side: task is done, result row exists
    db = models.SessionLocal()
    try:
        task = db.get(models.Task, task_id)
        assert task.status == "done"
        results = db.query(models.Result).filter(models.Result.task_id == task_id).all()
        assert len(results) == 1
        assert results[0].total == 2
    finally:
        db.close()


def test_cmd_pull_no_tasks(tmp_config, asgi_factory, capsys):
    """No pending tasks → prints '(no pending tasks)' and returns cleanly."""
    args = SimpleNamespace(server="http://testserver", user=None, password=None)
    cli.cmd_setup(args, client_factory=asgi_factory)

    cli.cmd_pull(SimpleNamespace(), client_factory=asgi_factory)

    out = capsys.readouterr().out
    assert "no pending tasks" in out


def test_cmd_pull_unconfigured_exits(tmp_config):
    """If client.id is empty, cmd_pull exits with code 1."""
    cli.save_config(cli.default_config())  # default has empty client.id
    with pytest.raises(SystemExit) as exc:
        cli.cmd_pull(SimpleNamespace())
    assert exc.value.code == 1


# ===== script auto-distribution =====

def test_apply_zip_writes_files(tmp_path):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a/b.txt", "hello")
        zf.writestr("c.txt", "world")

    n = cli._apply_zip(buf.getvalue(), tmp_path)
    assert n == 2
    assert (tmp_path / "a" / "b.txt").read_text() == "hello"
    assert (tmp_path / "c.txt").read_text() == "world"


def test_apply_zip_rejects_path_traversal(tmp_path):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../../evil.txt", "owned")

    with pytest.raises(ValueError, match="unsafe"):
        cli._apply_zip(buf.getvalue(), tmp_path)


def _patch_root(monkeypatch, root):
    monkeypatch.setattr(cli, "REPO_ROOT", root)
    monkeypatch.setattr(cli, "CONFIG_PATH", root / "client_config.json")


def test_cmd_update_first_time_downloads(tmp_path, monkeypatch, asgi_factory):
    _patch_root(monkeypatch, tmp_path)
    # tmp has no VERSION → local = 0.0.0; remote is repo's actual VERSION.

    cli.cmd_update(SimpleNamespace(force=False), client_factory=asgi_factory)

    assert (tmp_path / "VERSION").read_text().strip()  # version was written
    assert (tmp_path / "jobs" / "xhs_comments" / "main.py").exists()
    assert (tmp_path / "shared" / "chrome_utils.py").exists()
    assert (tmp_path / "requirements.txt").exists()
    # client.py is shipped via /api/script/download so update overwrites itself too.
    assert (tmp_path / "client.py").exists()
    assert (tmp_path / "client_menu.py").exists()
    assert (tmp_path / "start.bat").exists()


def test_cmd_update_already_up_to_date_skips(tmp_path, monkeypatch, asgi_factory, capsys):
    _patch_root(monkeypatch, tmp_path)
    with asgi_factory() as api:
        real_version = api.get_version()["version"]
    (tmp_path / "VERSION").write_text(real_version)

    cli.cmd_update(SimpleNamespace(force=False), client_factory=asgi_factory)

    out = capsys.readouterr().out
    assert f"已是最新版本 {real_version}" in out or f"already at {real_version}" in out
    # No download happened — jobs/ shouldn't have been created.
    assert not (tmp_path / "jobs").exists()


def test_cmd_update_force_redownloads(tmp_path, monkeypatch, asgi_factory):
    _patch_root(monkeypatch, tmp_path)
    with asgi_factory() as api:
        real_version = api.get_version()["version"]
    (tmp_path / "VERSION").write_text(real_version)

    cli.cmd_update(SimpleNamespace(force=True), client_factory=asgi_factory)

    # Force: download even though versions match.
    assert (tmp_path / "jobs" / "xhs_comments" / "main.py").exists()


# ===== chrome_user_data injection =====

def test_setup_persists_chrome_user_data(tmp_config, asgi_factory):
    args = SimpleNamespace(
        server="http://testserver", user=None, password=None,
        chrome_user_data="C:\\Test\\Chrome",
    )
    cli.cmd_setup(args, client_factory=asgi_factory)
    cfg = cli.load_config()
    assert cfg["client"]["chrome_user_data"] == "C:\\Test\\Chrome"


def test_apply_config_to_env_sets_chrome_dir(monkeypatch):
    monkeypatch.delenv("CHROME_USER_DATA_DIR", raising=False)
    cfg = cli.default_config()
    cfg["client"]["chrome_user_data"] = "C:\\Custom\\Path"
    cli._apply_config_to_env(cfg)
    assert os.environ["CHROME_USER_DATA_DIR"] == "C:\\Custom\\Path"


def test_pull_injects_chrome_dir_from_config(tmp_config, asgi_factory, monkeypatch):
    """cmd_pull should call _apply_config_to_env so the scraper imports see the right dir."""
    monkeypatch.delenv("CHROME_USER_DATA_DIR", raising=False)
    args = SimpleNamespace(
        server="http://testserver", user=None, password=None,
        chrome_user_data="C:\\Pull\\Chrome",
    )
    cli.cmd_setup(args, client_factory=asgi_factory)

    # No tasks pending, so cmd_pull short-circuits — but the env injection happens before that.
    cli.cmd_pull(SimpleNamespace(), client_factory=asgi_factory)
    assert os.environ["CHROME_USER_DATA_DIR"] == "C:\\Pull\\Chrome"


# ===== submit subcommand =====

def test_cmd_submit_creates_runs_uploads(tmp_config, asgi_factory, client):
    """End-to-end: cmd_submit posts a task, executes (mocked), uploads result with client_id."""
    args = SimpleNamespace(
        server="http://testserver", user=None, password=None,
        chrome_user_data=None,
    )
    cid = cli.cmd_setup(args, client_factory=asgi_factory)

    fake_result = {"total": 7, "items": [{"author": "x", "content": "y"}]}
    submit_args = SimpleNamespace(
        url="https://www.xiaohongshu.com/explore/abcd",
        job_type="xhs_comments",
        scrolls=2, delay=1.5,
    )
    with patch.object(cli, "execute_job", return_value=fake_result) as exec_mock:
        cli.cmd_submit(submit_args, client_factory=asgi_factory)

    # execute_job called with the URL we submitted + params
    job_type, url, params = exec_mock.call_args[0]
    assert job_type == "xhs_comments"
    assert url == "https://www.xiaohongshu.com/explore/abcd"
    assert params == {"scrolls": 2, "delay": 1.5}

    # Server-side: a task was created (status done after upload), result row carries client_id
    db = models.SessionLocal()
    try:
        tasks = db.query(models.Task).filter(models.Task.client_id == cid).all()
        assert len(tasks) == 1
        assert tasks[0].status == "done"
        assert tasks[0].url == "https://www.xiaohongshu.com/explore/abcd"

        results = db.query(models.Result).filter(models.Result.task_id == tasks[0].id).all()
        assert len(results) == 1
        assert results[0].total == 7
        assert results[0].client_id == cid
    finally:
        db.close()


def test_cmd_submit_unconfigured_exits(tmp_config):
    """submit without prior setup exits with code 1."""
    cli.save_config(cli.default_config())  # default has empty client.id
    args = SimpleNamespace(url="https://x", job_type="xhs_comments", scrolls=None, delay=None)
    with pytest.raises(SystemExit) as exc:
        cli.cmd_submit(args)
    assert exc.value.code == 1
