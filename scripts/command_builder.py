"""确定性指令构建编排器 — rpa_new_command 的执行体（零 LLM）。

把"新增指令"的确定性动作固化为一条命令，供 DSH 插件 rpa_new_command 工具 spawn：
  ① 写 commands/<cmd>.json（definition 必需，或校验已存在）
  ② 跑 generate_commands.py 生成桩（extension → py 桩 + JS handler）
  ③ 跑 build_content_js.py 拼装 content.js（extension 指令）
  ④ 校验：新指令在 content.js / Python registry 中确实就位
  ⑤ 质量门禁：跑 skills/scripts/check_command_quality.py <cmd>（--quality 默认开）
  ⑥ 热重载 + 校验：POST /api/commands/reload + validate（--reload 默认开）
  ⑦ 输出结构化结果（每步状态 + 校验报告 + 产物路径）

不调用 LLM：definition 由调用方（模型/人）先准备好，命令只做确定性的生成-落盘-校验。
用于 backend/control/desktop 指令时，② 会生成 Python 桩（若 runtime 非 extension 且
handler.kind=backend/control，则脚本 SKIP——按语义保留手写实现文件）。
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows 控制台默认 GBK，print(json.dumps(...)) 含中文/路径/子进程输出的 \ufffd 时会
# UnicodeEncodeError。强制 UTF-8 输出，保证本脚本的 JSON 结果稳定可被上游解析。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = ROOT / "commands"
GENERATE_SCRIPT = ROOT / "scripts" / "generate_commands.py"
BUILD_JS_SCRIPT = ROOT / "scripts" / "build_content_js.py"
CONTENT_JS = ROOT / "dist" / "desktop" / "extension" / "content.js"


def _run(cmd: list[str], timeout=120) -> tuple[int, str]:
    """运行子进程，返回 (exit_code, stdout+stderr)。"""
    try:
        p = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, shell=False,
        )
        out = (p.stdout or "") + (p.stderr or "")
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:  # noqa: BLE001
        return -1, f"SPAWN_ERROR: {e}"


def _write_definition(cmd: str, definition: dict) -> dict:
    """把 definition 写到 commands/<cmd>.json。已存在且未强制覆盖则报错。"""
    if not definition:
        return {"ok": False, "error": "缺少 definition（指令 JSON 定义）"}
    if not cmd:
        cmd = definition.get("cmd") or definition.get("type") or ""
    cmd = (cmd or "").strip()
    if not cmd:
        return {"ok": False, "error": "无法确定指令名（cmd）"}
    # 统一字段名：JSON 用 cmd（generate_commands 以 cmd 为键）
    definition = dict(definition)
    definition.setdefault("cmd", cmd)
    target = COMMANDS_DIR / f"{cmd}.json"
    if target.exists():
        return {"ok": False, "error": f"指令已存在: {target.name}", "path": str(target)}
    try:
        target.write_text(
            json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"写定义失败: {e}"}
    return {"ok": True, "cmd": cmd, "path": str(target)}


def _collect_commands(cmd: str) -> dict:
    """从 commands/*.json 读取指定指令的定义。"""
    target = COMMANDS_DIR / f"{cmd}.json"
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _run_quality_gate(cmd: str) -> dict:
    """跑质量门禁（skills/scripts/check_command_quality.py <cmd> --json），返回汇总。"""
    qg = ROOT / "skills" / "scripts" / "check_command_quality.py"
    if not qg.exists():
        return {"skip": True, "note": f"质量门禁脚本不存在: {qg}"}
    code, out = _run([sys.executable, str(qg), cmd, "--json"])
    try:
        data = json.loads(out)
    except Exception:  # noqa: BLE001
        return {"ok": False, "raw": out.strip()[-400:]}
    issues = [i for r in data.get("results", []) for i in r.get("issues", [])]
    return {"ok": data.get("ok", False), "error_count": len(issues), "issues": issues}


def _backend_port() -> int:
    """发现后端端口：优先 data/backend.port，回退 8100。"""
    try:
        pf = ROOT / "data" / "backend.port"
        if pf.exists():
            return int(pf.read_text(encoding="utf-8").strip() or 0)
    except Exception:  # noqa: BLE001
        pass
    return 8100


def _run_http_reload(cmd: str) -> dict:
    """热重载：POST /api/commands/reload + /validate，把新指令加载进运行时并校验。

    认证为免登录（get_current_user 恒放行），无需 token。返回汇总。
    """
    import urllib.request
    port = _backend_port()
    base = f"http://127.0.0.1:{port}"
    headers = {"Content-Type": "application/json"}
    steps = []

    def _post(path):
        req = urllib.request.Request(base + path, data=b"{}", headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")

    try:
        status, body = _post("/api/commands/reload")
        steps.append({"endpoint": "reload", "status": status})
        try:
            reload_data = json.loads(body)
            steps[-1]["handlers"] = reload_data.get("handlers")
            steps[-1]["local_handlers"] = reload_data.get("local_handlers")
        except Exception:  # noqa: BLE001
            steps[-1]["body"] = body[:200]
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"热重载失败（后端 {base} 可能未运行）: {e}",
                "steps": steps, "port": port}

    try:
        status, body = _post("/api/commands/validate")
        steps.append({"endpoint": "validate", "status": status})
        try:
            v = json.loads(body)
            steps[-1]["passed"] = v.get("passed")
        except Exception:  # noqa: BLE001
            steps[-1]["body"] = body[:200]
    except Exception as e:  # noqa: BLE001
        steps[-1]["error"] = str(e)

    all_ok = all(s.get("status") == 200 and s.get("passed") is not False for s in steps)
    return {"ok": all_ok, "steps": steps, "port": port}


def main():
    parser = argparse.ArgumentParser(description="确定性指令构建编排器")
    parser.add_argument("cmd", help="指令名（cmd）")
    parser.add_argument("--definition", default=None, help="定义的 JSON 字符串（可选）")
    parser.add_argument("--definition-file", default=None,
                        help="定义 JSON 文件路径（推荐：规避 Windows 命令行中文编码）")
    parser.add_argument("--skip-build-js", action="store_true",
                        help="跳过 build_content_js.py（非 extension 指令可省）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的定义文件")
    parser.add_argument("--no-quality", action="store_true",
                        help="跳过质量门禁（默认跑）")
    parser.add_argument("--no-reload", action="store_true",
                        help="跳过热重载 + 校验（默认跑）")
    args = parser.parse_args()

    cmd = args.cmd.strip()
    definition = None
    if args.definition_file:
        try:
            definition = json.loads(Path(args.definition_file).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"读取 definition 文件失败: {e}"}))
            sys.exit(1)
    elif args.definition:
        try:
            definition = json.loads(args.definition)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": f"definition 不是合法 JSON: {e}"}))
            sys.exit(1)

    result = {"cmd": cmd, "steps": []}

    # ① 写定义
    target = COMMANDS_DIR / f"{cmd}.json"
    if definition and target.exists() and not args.force:
        step = {"name": "write_definition", "ok": False,
                "error": f"指令已存在: {target.name}（用 --force 覆盖）"}
        result["steps"].append(step)
        result["ok"] = False
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    if definition:
        wr = _write_definition(cmd, definition)
        step = {"name": "write_definition", "ok": wr["ok"],
                "path": wr.get("path"), **({"error": wr["error"]} if not wr["ok"] else {})}
        result["steps"].append(step)
        if not wr["ok"]:
            result["ok"] = False
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
    else:
        # 未给 definition：校验并读取已存在定义
        existing = _collect_commands(cmd)
        if not existing:
            result["steps"].append({"name": "write_definition", "ok": False,
                                    "error": "缺少 definition 且 commands/<cmd>.json 不存在"})
            result["ok"] = False
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
        result["steps"].append({"name": "write_definition", "ok": True,
                                "note": "使用已存在的定义文件", "path": str(target)})

    defn = _collect_commands(cmd)
    runtime = defn.get("runtime", "")
    handler_kind = (defn.get("handler") or {}).get("kind", "")

    # ② 生成桩（generate_commands 遍历全量，幂等）
    code, out = _run([sys.executable, str(GENERATE_SCRIPT)])
    gen_ok = code == 0
    step = {"name": "generate_commands", "ok": gen_ok, "exit": code}
    # 检查生成产物是否落位
    py_dir = ROOT / "src" / "runtime" / "commands" / f"{runtime or 'extension'}_commands"
    py_path = py_dir / f"{cmd}.py"
    if gen_ok and py_path.exists():
        step["py"] = str(py_path)
    else:
        # 未落位（可能 SKIP 或路径不同），记录输出供排查
        step["hint"] = out.strip()[-400:] if out.strip() else ""
    result["steps"].append(step)
    if not gen_ok:
        result["ok"] = False
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    # ③ 拼装 content.js（仅 extension 且有 JS 时）
    js_registered = False
    if runtime == "extension" and not args.skip_build_js:
        bcode, bout = _run([sys.executable, str(BUILD_JS_SCRIPT)])
        step = {"name": "build_content_js", "ok": bcode == 0, "exit": bcode}
        if CONTENT_JS.exists():
            content = CONTENT_JS.read_text(encoding="utf-8")
            js_registered = f"registerHandler('{cmd}'" in content or \
                            f'registerHandler("{cmd}"' in content or \
                            f"registerHandler('{cmd}'" in content
            step["content_js"] = str(CONTENT_JS)
            step["registered_in_content_js"] = js_registered
        result["steps"].append(step)
        if not bcode:
            result["ok"] = False
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
    elif runtime == "extension":
        result["steps"].append({"name": "build_content_js", "ok": True, "skipped": True})

    # ④ 校验：Python registry 是否声明该指令（backend/control 走手工注册，需重启后加载）
    try:
        sys.path.insert(0, str(ROOT))
        from src.runtime.commands import auto_register
        auto_register()
        from src.runtime.workflow.handler_registry import get_all_handlers
        handlers = get_all_handlers()
        registered = cmd in handlers
        result["steps"].append({
            "name": "validate_registry", "ok": registered,
            "registered_in_python": registered,
            "note": ("已注册" if registered else
                     "Python 注册未就位（backend/control 需重启后端加载；extension 桩已生成）"),
        })
    except Exception as e:  # noqa: BLE001
        result["steps"].append({"name": "validate_registry", "ok": False, "error": f"{e}"})

    # ⑤ 质量门禁（默认开；--no-quality 跳过）
    if not args.no_quality:
        qg = _run_quality_gate(cmd)
        result["steps"].append({"name": "quality_gate", **qg})

    # ⑥ 热重载 + 校验（默认开；--no-reload 跳过）
    if not args.no_reload:
        rl = _run_http_reload(cmd)
        result["steps"].append({"name": "reload_validate", **rl})
        # reload 失败通常因后端未运行——不计入构建失败，提示即可
        if "error" in rl:
            result["reload_warning"] = rl["error"]

    # 汇总 ok：反映"骨架文件落盘成功"（write_definition/generate_commands/build_js/registry）。
    # quality_gate/reload 的通过情况独立返回（quality_pass），不反过来置 ok=false——
    # 生成骨架这一步，scaffold 的 extra.get("paramName") 是合法的占位，实现未填时门禁
    # 会报，属预期；LLM 填完实现再跑一次本命令即可让门禁转绿。
    core_steps = ("write_definition", "generate_commands", "build_content_js", "validate_registry")
    result["ok"] = all(s.get("ok", False) for s in result["steps"] if s.get("name") in core_steps)
    qg_step = next((s for s in result["steps"] if s.get("name") == "quality_gate"), None)
    if qg_step:
        result["quality_pass"] = bool(qg_step.get("ok")) or bool(qg_step.get("skip"))
        result["quality_issues"] = qg_step.get("issues", [])
    rl_step = next((s for s in result["steps"] if s.get("name") == "reload_validate"), None)
    if rl_step:
        result["reload_pass"] = bool(rl_step.get("ok"))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
