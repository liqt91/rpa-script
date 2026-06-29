"""Job registry: scan, validation, hot reload, legacy compatibility."""

import time

from src.runtime.job_registry import JobRegistry
from src.config import settings as config


def test_scan_finds_hello_world():
    registry = JobRegistry(config.JOBS_DIR)
    meta = registry.get_job("hello_world")
    assert meta is not None
    assert meta.name == "hello_world"
    assert meta.version == "1.0.0"
    assert "name" in meta.params


def test_validate_params_ok():
    registry = JobRegistry(config.JOBS_DIR)
    ok, errors = registry.validate_params("hello_world", {"name": "test"})
    assert ok is True
    assert errors == []


def test_validate_params_default_values():
    """使用默认值（空 params）应通过。"""
    registry = JobRegistry(config.JOBS_DIR)
    ok, errors = registry.validate_params("hello_world", {})
    assert ok is True
    assert errors == []


def test_validate_params_type_error():
    registry = JobRegistry(config.JOBS_DIR)
    ok, errors = registry.validate_params("hello_world", {"name": 123})
    assert ok is False
    assert any("应为 string" in e or "应为" in e for e in errors)


def test_validate_params_unknown_param():
    registry = JobRegistry(config.JOBS_DIR)
    ok, errors = registry.validate_params("hello_world", {"unknown": 1})
    assert ok is False
    assert any("未知参数" in e for e in errors)


def test_validate_params_unknown_job():
    registry = JobRegistry(config.JOBS_DIR)
    ok, errors = registry.validate_params("nonexistent_job", {})
    assert ok is False
    assert any("未知脚本" in e for e in errors)


def test_legacy_job_no_validation(tmp_path):
    """没有 job.yaml 的脚本不校验参数。"""
    jobs_dir = tmp_path / "jobs"
    legacy_dir = jobs_dir / "legacy_job"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "main.py").write_text("def run(url, **params): pass")

    registry = JobRegistry(str(jobs_dir))
    ok, errors = registry.validate_params("legacy_job", {"anything": "goes"})
    assert ok is True
    assert errors == []


def test_hot_reload(tmp_path):
    """新增 job.yaml 后 check_reload 能发现新脚本。"""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()

    registry = JobRegistry(str(jobs_dir))
    assert registry.get_job("new_job") is None

    # 模拟新增脚本
    time.sleep(0.1)
    new_dir = jobs_dir / "new_job"
    new_dir.mkdir()
    (new_dir / "job.yaml").write_text("name: new_job\nversion: 1.0.0\n")
    (new_dir / "main.py").write_text("def run(url, **params): pass")

    registry.check_reload()
    meta = registry.get_job("new_job")
    assert meta is not None
    assert meta.name == "new_job"
    assert meta.version == "1.0.0"
