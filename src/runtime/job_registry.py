"""
脚本注册表：扫描 jobs/ 目录、解析 job.yaml、维护内存缓存、参数验证。
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from src.config import runtime_config as config
from .schemas import ScriptMeta, ParamConstraint, ScriptParam


class JobRegistry:
    """
    内存缓存 + mtime 热加载的脚本注册表。
    首次访问时扫描 jobs/，后续通过 check_reload() 检测文件变化。
    """

    def __init__(self, jobs_dir: str | Path):
        self.jobs_dir = Path(jobs_dir)
        self._cache: dict[str, ScriptMeta] = {}
        self._mtime: float = 0.0
        self._scan()

    # ---------- 扫描 ----------

    def _scan(self) -> None:
        """扫描 jobs/ 下所有子目录，解析 job.yaml。"""
        self._cache.clear()
        if not self.jobs_dir.exists():
            return

        for entry in self.jobs_dir.iterdir():
            if not entry.is_dir():
                continue
            job_name = entry.name
            # 跳过隐藏目录和特殊目录
            if job_name.startswith(".") or job_name.startswith("_"):
                continue
            yaml_path = entry / "job.yaml"
            if yaml_path.exists():
                meta = self._parse_job_yaml(yaml_path)
            else:
                meta = self._infer_legacy_meta(entry)
            if meta is not None and meta.enabled:
                meta.requirements = self._read_requirements(entry)
                self._cache[job_name] = meta

        self._mtime = self._jobs_dir_mtime()

    def _parse_job_yaml(self, path: Path) -> Optional[ScriptMeta]:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return ScriptMeta(**data)
        except Exception:
            # 解析失败则跳过该脚本，不影响其他
            return None

    def _infer_legacy_meta(self, entry: Path) -> ScriptMeta:
        """向后兼容：没有 job.yaml 的脚本，生成最小化元数据。"""
        return ScriptMeta(
            name=entry.name,
            version="0.0.0",
            description=f"Legacy script: {entry.name}",
            params={},
            enabled=True,
        )

    def _read_requirements(self, entry: Path) -> list[str]:
        """读取脚本目录下的 requirements.txt，返回非空行列表。"""
        req_path = entry / "requirements.txt"
        if not req_path.exists():
            return []
        try:
            with open(req_path, encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception:
            return []

    def _jobs_dir_mtime(self) -> float:
        """取 jobs/ 下所有 job.yaml / main.py 的最新 mtime，用于热加载判断。"""
        mtimes = [0.0]
        if not self.jobs_dir.exists():
            return 0.0
        for entry in self.jobs_dir.iterdir():
            if not entry.is_dir():
                continue
            yaml_path = entry / "job.yaml"
            main_path = entry / "main.py"
            if yaml_path.exists():
                mtimes.append(yaml_path.stat().st_mtime)
            elif main_path.exists():
                mtimes.append(main_path.stat().st_mtime)
        return max(mtimes)

    # ---------- 热加载 ----------

    def check_reload(self) -> None:
        """检测是否需要重新扫描。在路由端点中显式调用。"""
        current = self._jobs_dir_mtime()
        if current > self._mtime:
            self._scan()

    # ---------- 查询 ----------

    def list_jobs(self) -> list[ScriptMeta]:
        self.check_reload()
        return list(self._cache.values())

    def get_job(self, name: str) -> Optional[ScriptMeta]:
        self.check_reload()
        return self._cache.get(name)

    def has_job(self, name: str) -> bool:
        self.check_reload()
        return name in self._cache

    # ---------- 参数校验 ----------

    def validate_params(self, job_name: str, params: dict) -> tuple[bool, list[str]]:
        """
        验证参数。返回 (是否通过, 错误消息列表)。
        无 schema 的 legacy 脚本始终通过。
        """
        meta = self.get_job(job_name)
        if not meta:
            return False, [f"未知脚本类型: {job_name}"]
        if not meta.params:
            return True, []

        errors: list[str] = []
        # 检查必填
        for key, schema in meta.params.items():
            if schema.required and key not in params:
                errors.append(f"缺少必填参数: {key}")

        # 检查已知参数
        for key, value in params.items():
            if key not in meta.params:
                errors.append(f"未知参数: {key}")
                continue
            schema = meta.params[key]
            err = self._validate_one_param(key, value, schema)
            if err:
                errors.append(err)

        return len(errors) == 0, errors

    def _validate_one_param(
        self, key: str, value: Any, schema: ScriptParam
    ) -> Optional[str]:
        # 类型检查
        type_map = {
            "string": str,
            "integer": int,
            "float": (int, float),
            "boolean": bool,
            "url": str,
            "enum": (str, int, float, bool),
        }
        expected = type_map.get(schema.type)
        if expected is not None and not isinstance(value, expected):
            # float 同时接受 int，但 integer 不接受 float
            if schema.type == "integer" and isinstance(value, float):
                if not value.is_integer():
                    return f"参数 '{key}' 应为整数，得到 {type(value).__name__}"
                value = int(value)
            elif schema.type == "float" and isinstance(value, int):
                pass  # int 可以接受作为 float
            else:
                return f"参数 '{key}' 应为 {schema.type}，得到 {type(value).__name__}"

        # constraints 检查
        c = schema.constraints
        if c is None:
            return None

        # 数值范围
        numeric_types = (int, float)
        if isinstance(value, numeric_types):
            if c.min is not None and value < c.min:
                return f"参数 '{key}' 必须 >= {c.min}"
            if c.max is not None and value > c.max:
                return f"参数 '{key}' 必须 <= {c.max}"

        # 字符串正则
        if c.pattern and schema.type in ("string", "url") and isinstance(value, str):
            if not re.match(c.pattern, value):
                return f"参数 '{key}' 格式不匹配: {c.pattern}"

        # 枚举
        if c.choices and value not in c.choices:
            return f"参数 '{key}' 必须是以下之一: {c.choices}"

        return None


# ---------- 全局单例 ----------

_registry: Optional[JobRegistry] = None


def get_registry() -> JobRegistry:
    global _registry
    if _registry is None:
        _registry = JobRegistry(config.JOBS_DIR)
    return _registry
