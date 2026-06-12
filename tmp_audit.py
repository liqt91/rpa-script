"""Command consistency audit (Phase 1)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from runtime.workflow.commands import COMMAND_REGISTRY, get_container_types, get_structural_types, get_branch_types
from runtime.workflow.emitters._registry import _EMIT_HANDLERS

# Import emitter modules to ensure registration
from runtime.workflow import emitters  # noqa


def registry_enabled():
    return {t: c for t, c in COMMAND_REGISTRY.items() if c.get("enabled")}


def extract_js_handlers():
    text = (ROOT / "extension" / "content.js").read_text(encoding="utf-8")
    m = re.search(r"const handlers = \{", text)
    if not m:
        return set()
    start = m.end() - 1
    depth = 1
    i = start + 1
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    body = text[start + 1 : i - 1]
    keys = set()
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            continue
        if depth == 0:
            mm = re.match(r"(?:async\s+)?(\w+)\s*\(", stripped)
            if mm and mm.group(1) not in {"if", "while", "for", "switch", "catch", "with"}:
                keys.add(mm.group(1))
        # update depth for braces (ignore string braces)
        in_str = False
        esc = False
        schar = None
        for ch in line:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if in_str:
                if ch == schar:
                    in_str = False
                continue
            if ch in ('"', "'"):
                in_str = True
                schar = ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
    return keys


def extract_runner_local_handlers():
    text = (ROOT / "src" / "runtime" / "workflow" / "extension_runner.py").read_text(encoding="utf-8")
    # Extract strings inside _handle_local
    m = re.search(r"async def _handle_local\(self.*?\n(?=    async def _execute_instruction|\Z)", text, re.S)
    if not m:
        return set()
    block = m.group(0)
    return set(re.findall(r'if cmd_type == "([^"]+)"', block))


def extract_nodelist_cases():
    text = (ROOT / "src" / "ui" / "workflow-editor" / "src" / "components" / "NodeList.jsx").read_text(encoding="utf-8")
    return set(re.findall(r"case '([^']+)':", text))


def extract_md_commands():
    path = ROOT / "commands_table.md"
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    cmds = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and not line.startswith("|---") and "命令类型" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) > 1 and parts[1]:
                cmds.add(parts[1])
    return cmds


def main():
    reg = registry_enabled()
    reg_types = set(reg)
    # map command -> handler name
    cmd_to_js = {}
    for t, c in reg.items():
        ext = c.get("runtimes", {}).get("extension")
        if ext and not ext.get("local"):
            cmd_to_js[t] = ext.get("handler")
    js_handler_names = set(cmd_to_js.values())
    local_types = {t for t, c in reg.items() if c.get("runtimes", {}).get("extension", {}).get("local")}
    container_types = set(get_container_types())
    structural_types = set(get_structural_types())
    branch_types = set(get_branch_types())

    js_handlers = extract_js_handlers()
    runner_locals = extract_runner_local_handlers()
    nodelist_cases = extract_nodelist_cases()
    md_cmds = extract_md_commands()
    emit_handlers = set(_EMIT_HANDLERS)

    issues = []

    # 1. Commands with extension handler name missing in content.js
    missing_js = [f"{cmd}->{hnd}" for cmd, hnd in cmd_to_js.items() if hnd not in js_handlers]
    if missing_js:
        issues.append(f"[Runtime→JS] Extension handler missing in content.js: {sorted(missing_js)}")

    # 2. JS handlers not referenced by any enabled command's runtime
    used_js = js_handler_names | {"checkElementExists", "checkElementVisible", "findElements", "getElementText"}
    unused_js = js_handlers - used_js
    if unused_js:
        issues.append(f"[JS→Runtime] content.js handlers with no enabled command: {sorted(unused_js)}")

    # 3. Local commands missing handler in extension_runner.py
    missing_local = local_types - runner_locals
    if missing_local:
        issues.append(f"[Local→Runner] Local commands missing handler in extension_runner.py: {sorted(missing_local)}")

    # 4. Runner local handlers for commands not in registry/local
    orphan_local = runner_locals - local_types
    if orphan_local:
        issues.append(f"[Runner→Local] Local handlers for non-local/non-existent commands: {sorted(orphan_local)}")

    # 5. Commands missing runtime declaration (should have one unless container/structural/branch/break/continue)
    no_runtime = []
    for t, c in reg.items():
        if t in container_types | structural_types | branch_types | {"break", "continue"}:
            continue
        if not c.get("runtimes"):
            no_runtime.append(t)
    if no_runtime:
        issues.append(f"[Registry] Enabled commands missing runtime declaration: {sorted(no_runtime)}")

    # 6. Emitters missing for commands that need Python export
    emitter_expected = reg_types - container_types - structural_types - branch_types - {"break", "continue"}
    missing_emitter = emitter_expected - emit_handlers
    if missing_emitter:
        issues.append(f"[Registry→Emitter] Commands missing Python emitter: {sorted(missing_emitter)}")

    # 7. Emitter handlers for deleted/non-enabled commands
    orphan_emitter = emit_handlers - reg_types
    if orphan_emitter:
        issues.append(f"[Emitter→Registry] Emitter handlers for removed/disabled commands: {sorted(orphan_emitter)}")

    # 8. NodeList description-overrides for removed commands
    orphan_nodelist = nodelist_cases - reg_types
    if orphan_nodelist:
        issues.append(f"[UI→Registry] NodeList cases without registry command: {sorted(orphan_nodelist)}")

    # 9. commands_table.md stale entries
    stale_md = md_cmds - reg_types
    if stale_md:
        issues.append(f"[Docs→Registry] commands_table.md lists removed commands: {sorted(stale_md)}")

    print(f"Audit summary: {len(reg)} enabled commands, {len(js_handlers)} JS handlers, "
          f"{len(runner_locals)} local handlers, {len(emit_handlers)} emitters, {len(nodelist_cases)} NodeList cases, {len(md_cmds)} md rows")
    if issues:
        print(f"\n{len(issues)} issue groups:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("\nNo issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
