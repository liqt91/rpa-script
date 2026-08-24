#!/usr/bin/env python3
"""指令生成质量门禁（可执行自检）— 供 new-command / check-command skill 复用。

对指定指令（或全量）做"生成后质量检查"，把 AI 生成指令时易犯的规范问题
固化为可执行规则。返回 JSON，供 skill / 插件 / 命令链读取。

检查项（problem-in-source 优先；与项目真实执行语义对齐）：
  - def_required : JSON 必需字段（cmd/label/runtime）
  - def_fields   : cmd 与文件名一致、camelCase、runtime/handler.kind 合法、source 目录合理
  - impl_exists  : handler.source 指向的 .py 存在
  - reg_params   : @register_handler params 名与 JSON params[].name 对齐（$ref 已展开）
  - extra_refs   : execute() 里 extra.get(...) 引用 == JSON params[].name（composite 豁免——执行时注入 locator 等）
  - sentinel     : 手写 backend/desktop/control 文件不得残留 AUTO-GENERATED 哨兵注释
  - execute      : 非容器 backend/desktop 必须有 async def execute()
  - emit         : 非容器指令成功路径必须有 runner.completed += 1（completedSteps 计数）
  - summary_tpl  : 有 source 且非纯注册桩时，建议提供 summary_tpl（不强制）

注：不含 resolve_vars 检查——runner 在调用 handler 前对 extra 统一 _resolve_vars（见
extension_runner._handle_compound / _evaluate_condition），execute 内单独调用是冗余。

用法:
  python skills/scripts/check_command_quality.py [cmd ...] [--all] [--json]
    [cmd ...]  检查指定指令（commands/<cmd>.json）；不带参数默认全量
    --all      检查全部指令
    --json     输出机器可读 JSON
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Windows 控制台默认 GBK，✓/✗/中文会 UnicodeEncodeError。强制 UTF-8 输出。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent.parent  # skills/scripts/ → repo root
COMMANDS_DIR = ROOT / "commands"
VALID_RUNTIME = {"extension", "backend", "control"}
VALID_KIND = {"extension", "backend", "control"}
# extension 指令合法的 source 目录（前台上文 dom_handlers_new / 后台 background_handlers / python 桩 extension_commands）
EXT_SOURCE_OK = ("extension_commands", "dom_handlers", "background_handlers")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"__error__": str(e), "__path__": str(path)}


def _resolve_py_path(defn):
    """根据 handler.source / kind / runtime 推断 .py 文件路径。"""
    handler = defn.get("handler") or {}
    source = handler.get("source", "")
    if source:
        if (ROOT / source).exists():
            return ROOT / source
        if Path(source).exists():
            return Path(source)
        base = Path(source)
        if base.suffix != ".py":
            return None
        return ROOT / base if base.is_absolute() else ROOT / base
    # 缺 source 时按 kind（或 runtime 兜底）猜目录
    kind = handler.get("kind", "") or defn.get("runtime", "")
    if kind == "extension":
        return ROOT / "src" / "runtime" / "commands" / "extension_commands" / f"{defn['cmd']}.py"
    if kind == "backend":
        p1 = ROOT / "src" / "runtime" / "commands" / "backend_commands" / f"{defn['cmd']}.py"
        p2 = ROOT / "src" / "runtime" / "commands" / "desktop_commands" / f"{defn['cmd']}.py"
        return p1 if p1.exists() else p2
    if kind == "control":
        return ROOT / "src" / "runtime" / "commands" / "control_commands" / f"{defn['cmd']}.py"
    return None


def _json_params(defn):
    """JSON params（展开 $ref 共享参数，与 generate_commands/resolve_params 一致）。"""
    raw = defn.get("params") or []
    try:
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        from src.runtime.workflow.param_options import resolve_params
        raw = resolve_params(list(raw))
    except Exception:  # noqa: BLE001 —— 展开失败时回退原始 params（不静默吞掉可见性）
        pass
    return [p for p in raw if isinstance(p, dict)]


def check_one(defn, path: Path) -> dict:
    issues = []
    meta = {"file": path.name, "runtime": defn.get("runtime", ""), "kind": (defn.get("handler") or {}).get("kind", "")}

    # 1. def_required（handler.kind 允许缺省——control/extension 由 runtime 推断）
    for field in ("cmd", "label", "runtime"):
        if not defn.get(field):
            issues.append({"rule": "def_required", "msg": f"缺少必需字段 {field}"})

    cmd = defn.get("cmd", "")
    runtime = defn.get("runtime", "")
    # kind 缺省时用 runtime 推断（控制流/容器指令通常只写 runtime）
    kind = meta["kind"] or runtime
    is_container = bool(defn.get("isContainer"))
    # 存量 legacy：source 指向旧 handler 系统（handlers/...），实际注册走新目录同名 .py。
    # 这类已知豁免：不按 source 判实现缺失/目录不一致，避免误报存量。
    source_raw = (defn.get("handler") or {}).get("source", "")
    is_legacy = "handlers/" in source_raw

    # 2. def_fields
    if cmd:
        if not re.match(r"^[a-z][a-zA-Z0-9]*$", cmd):
            issues.append({"rule": "def_fields", "msg": f"cmd '{cmd}' 非 camelCase（应小写开头驼峰）"})
        if path.stem != cmd:
            issues.append({"rule": "def_fields", "msg": f"文件名 {path.name} != cmd '{cmd}'"})
    if runtime and runtime not in VALID_RUNTIME:
        issues.append({"rule": "def_fields", "msg": f"runtime '{runtime}' 非法（可选 extension/backend/control）"})
    if kind and kind not in VALID_KIND:
        issues.append({"rule": "def_fields", "msg": f"handler.kind '{kind}' 非法"})
    if runtime and kind and runtime != kind:
        issues.append({"rule": "def_fields", "msg": f"runtime '{runtime}' != handler.kind '{kind}'"})
    # source 目录与 kind 一致（legacy 豁免；extension 放宽到前台/后台/桩三类目录）
    source = source_raw
    if source and not is_legacy:
        if kind == "extension":
            if not any(x in source for x in EXT_SOURCE_OK):
                issues.append({"rule": "def_fields",
                               "msg": f"extension source '{source}' 不在合法目录（应含 {EXT_SOURCE_OK}）"})
        else:
            dirmap = {"backend": ["backend_commands", "desktop_commands"],
                      "control": ["control_commands"]}
            allowed = dirmap.get(kind, [])
            if allowed and not any(x in source for x in allowed):
                issues.append({"rule": "def_fields", "msg": f"source '{source}' 与 kind '{kind}' 目录不一致（应含 {allowed}）"})

    # 3. impl_exists（legacy：注册靠新目录同名 .py，不按旧 source 判缺失）
    py_path = _resolve_py_path(defn)
    if is_legacy:
        # 后台 backend 指令实际实现按 kind 目录找
        py_path = ROOT / "src" / "runtime" / "commands" / f"{kind}_commands" / f"{cmd}.py"
        if not py_path.exists() and kind == "backend":
            alt = ROOT / "src" / "runtime" / "commands" / "desktop_commands" / f"{cmd}.py"
            py_path = alt if alt.exists() else py_path
    impl_ok = py_path is not None and py_path.exists()
    if kind in ("backend", "control") and not impl_ok and not is_legacy:
        issues.append({"rule": "impl_exists", "msg": f"实现文件不存在: {py_path}"})

    # 4-7 需要读到 Py 源码
    py_src = ""
    if py_path and py_path.exists():
        py_src = py_path.read_text(encoding="utf-8")

    if py_src:
        json_params = {p["name"] for p in _json_params(defn) if p.get("name")}
        has_execute = "def execute" in py_src
        has_evaluate = "async def evaluate" in py_src or "def evaluate" in py_src
        # 复合/容器/结构指令：由 emitter 展开，用 evaluate() 或 raise LoopBreak 控制流，
        # 不走标准 execute → 不要求 execute/emit/extra_refs 严格与 JSON params 对齐。
        composites = {"if", "while", "for", "try", "break", "continue", "end"}
        is_composite = (is_container or has_evaluate or kind == "control"
                        or any(cmd.startswith(x) for x in composites))

        # reg_params: Python @register_handler params vs JSON
        # （extension 后台指令 params 在 background JS 侧声明，Python 桩不全；composite 不强制）
        if kind in ("backend", "control") and not is_composite:
            py_params = set(re.findall(r"Param\(\s*[\"'](\w+)[\"']", py_src))
            missing = json_params - py_params
            extra = py_params - json_params
            if missing:
                issues.append({"rule": "reg_params", "msg": f"params 缺失（JSON 有但 Python 无）: {sorted(missing)}"})
            if extra:
                issues.append({"rule": "reg_params", "msg": f"params 冗余（Python 有但 JSON 无）: {sorted(extra)}"})

        # extra_refs: execute 里 extra.get 引用 vs JSON params（composite 豁免——执行时注入 locator 等）
        if has_execute and not is_composite:
            extra_refs = set(re.findall(r"extra\.get\(\s*[\"'](\w+)[\"']", py_src))
            unknown = extra_refs - json_params
            if unknown:
                issues.append({"rule": "extra_refs", "msg": f"extra.get 引用不在 JSON params: {sorted(unknown)}"})

        # sentinel: 手写 backend/desktop/control 不得残留 AUTO-GENERATED
        if kind in ("backend", "control") and "AUTO-GENERATED" in py_src:
            issues.append({"rule": "sentinel", "msg": "手写实现文件残留 AUTO-GENERATED 哨兵注释（应删除，避免误导）"})

        # execute / emit（composite 用 evaluate；非结构 backend/desktop 必须有 execute + completed）
        if kind in ("backend", "control") and not is_composite and not has_execute:
            issues.append({"rule": "execute", "msg": "backend/control 指令缺少 async def execute()"})
        if has_execute and not is_composite:
            if "runner._emit" not in py_src:
                issues.append({"rule": "emit", "msg": "execute 成功路径缺 runner._emit(stepComplete)（运行日志无法呈现）"})
            if "runner.completed" not in py_src:
                issues.append({"rule": "emit", "msg": "execute 缺 runner.completed 递增（completedSteps 计数会不准）"})
        if has_execute and "runner._emit" in py_src and "stepComplete" not in py_src:
            issues.append({"rule": "emit", "msg": "runner._emit 缺少 stepComplete 事件（运行日志无完成记录）"})

    return {"cmd": cmd, "file": path.name, "runtime": meta["runtime"], "kind": meta["kind"],
            "ok": not issues, "issues": issues}


def main():
    parser = argparse.ArgumentParser(description="指令生成质量门禁")
    parser.add_argument("cmds", nargs="*", help="要检查的指令名（commands/<cmd>.json）")
    parser.add_argument("--all", action="store_true", help="检查全部指令")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    if args.all or (not args.cmds):
        files = sorted(COMMANDS_DIR.glob("*.json"))
    else:
        files = [COMMANDS_DIR / f"{c}.json" for c in args.cmds]

    results = []
    for f in files:
        if not f.exists():
            results.append({"cmd": f.stem, "file": f.name, "runtime": "", "kind": "",
                            "ok": False, "issues": [{"rule": "def_required", "msg": f"文件不存在: {f}"}]})
            continue
        defn = _read_json(f)
        if "__error__" in defn:
            results.append({"cmd": f.stem, "file": f.name, "runtime": "", "kind": "",
                            "ok": False, "issues": [{"rule": "def_required", "msg": f"JSON 解析失败: {defn['__error__']}"}]})
            continue
        results.append(check_one(defn, f))

    all_ok = all(r["ok"] for r in results)
    summary = {"ok": all_ok, "total": len(results), "checked": len(results), "results": results}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "✓" if r["ok"] else "✗"
            print(f"{mark} {r['file']:<28} runtime={r['runtime']:<10} kind={r['kind']}")
            for i in r["issues"]:
                print(f"      [{i['rule']}] {i['msg']}")
        print(f"\n{'ALL PASS' if all_ok else 'HAS ISSUES'} ({len(results)} checked)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
