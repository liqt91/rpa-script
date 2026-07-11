"""
Workflow command CRUD + CSV export.
"""

import csv
import io
import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import auth
from src.repo import runtime_models as models
from src.shared.datetime_utils import parse_iso_datetime
from src.runtime.workflow.handlers.registry import get_command, list_categories, get_container_types
from ..workflow.validation import validate, extract_js_handler_names

router = APIRouter(prefix="/api/commands", tags=["commands"])


def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_commands(
    category: str = Query(None),
    enabled_only: bool = Query(True),
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    q = db.query(models.WorkflowCommand)
    if enabled_only:
        q = q.filter(models.WorkflowCommand.enabled == 1)
    if category:
        q = q.filter(models.WorkflowCommand.category == category)
    rows = q.order_by(
        models.WorkflowCommand.category_order,
        models.WorkflowCommand.command_order,
    ).all()
    result = []
    for r in rows:
        row = {
            "id": r.id,
            "type": r.type,
            "label": r.label,
            "category": r.category,
            "icon": r.icon,
            "iconColor": r.icon_color,
            "bgColor": r.bg_color,
            "isContainer": bool(r.is_container),
            "isBranch": bool(r.is_branch),
            "isStructural": bool(r.is_structural),
            "closesWith": r.closes_with,
            "fields": json.loads(r.fields) if r.fields else [],
            "handler": r.handler,
            "local": bool(r.local) if r.local is not None else None,
            "description": r.description or "",
            "isBuiltin": bool(r.is_builtin),
            "enabled": bool(r.enabled),
            "categoryOrder": r.category_order,
            "commandOrder": r.command_order,
            "reviewedAt": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
            "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
        }
        # 从 handler 注册表补充运行时元数据
        from src.runtime.workflow.handlers.registry import get_handler
        h = get_handler(r.type)
        if h:
            row["hasRuntime"] = h["runtime"] != "control"
            row["isContainer"] = h.get("isContainer")
            row["isBranch"] = h.get("isBranch")
            row["isStructural"] = h.get("isStructural")
            row["closesWith"] = h.get("closesWith")
        result.append(row)
    return result


@router.post("/reload-emitters")
def reload_emitters(user=Depends(auth.get_current_user)):
    """Runtime reload of emit handlers without server restart."""
    from src.runtime.workflow.emitters import reload_handlers
    reload_handlers()
    return {"success": True}


@router.post("/reload")
def reload_commands_endpoint(user=Depends(auth.get_current_user)):
    """Runtime reload — handler registry is auto-reloaded on import."""
    from src.runtime.workflow.emitters import reload_handlers
    reload_handlers()
    return {"success": True, "note": "handler registry auto-reloads on module reimport"}


@router.post("/validate")
def validate_commands(user=Depends(auth.get_current_user)):
    """Run the command-registry consistency validator and return its output."""
    passed, messages = validate()
    stdout = "\n".join(messages) if messages else "COMMAND VALIDATION PASSED"
    return {
        "passed": passed,
        "stdout": stdout,
        "stderr": "",
    }


@router.post("/sync-check")
def check_handler_sync(user=Depends(auth.get_current_user)):
    """校验 Python handler 声明与 content.js 实现是否一致。"""
    from src.runtime.workflow.handler_validator import validate_handler_sync
    passed, messages = validate_handler_sync()
    return {
        "passed": passed,
        "messages": messages,
    }


@router.post("")
def create_command(payload: dict[str, Any], db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    type_name = payload.get("type", "").strip()
    if not type_name:
        raise HTTPException(status_code=400, detail="type is required")
    existing = db.query(models.WorkflowCommand).filter(models.WorkflowCommand.type == type_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Command '{type_name}' already exists")

    cmd = models.WorkflowCommand(
        type=type_name,
        label=payload.get("label", type_name),
        category=payload.get("category", "其他"),
        icon=payload.get("icon", "fa-circle"),
        icon_color=payload.get("iconColor", "text-gray-500"),
        bg_color=payload.get("bgColor", "bg-gray-50"),
        is_container=1 if payload.get("isContainer") else 0,
        is_branch=1 if payload.get("isBranch") else 0,
        is_structural=1 if payload.get("isStructural") else 0,
        closes_with=payload.get("closesWith") or None,
        fields=json.dumps(payload.get("fields", [])),
        description=payload.get("description", ""),
        handler=payload.get("handler") or None,
        local=1 if payload.get("local") else 0,
        is_builtin=0,
        enabled=1 if payload.get("enabled", True) else 0,
        category_order=int(payload.get("categoryOrder", 0)),
        command_order=int(payload.get("commandOrder", 0)),
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    return {"id": cmd.id, "type": cmd.type}


@router.put("/{cmd_id}")
def update_command(
    cmd_id: int,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    user=Depends(auth.get_current_user),
):
    cmd = db.get(models.WorkflowCommand, cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    # Built-in commands: restrict mutable fields
    if cmd.is_builtin:
        allowed = {
            "label", "category", "icon", "iconColor", "bgColor",
            "fields", "enabled", "reviewedAt", "handler", "local", "description",
            "categoryOrder", "commandOrder", "closesWith",
        }
        payload = {k: v for k, v in payload.items() if k in allowed}

    for field, col in [
        ("label", "label"),
        ("category", "category"),
        ("icon", "icon"),
        ("iconColor", "icon_color"),
        ("bgColor", "bg_color"),
        ("description", "description"),
    ]:
        if field in payload:
            setattr(cmd, col, payload[field])

    if "isContainer" in payload:
        cmd.is_container = 1 if payload["isContainer"] else 0
    if "isBranch" in payload:
        cmd.is_branch = 1 if payload["isBranch"] else 0
    if "isStructural" in payload:
        cmd.is_structural = 1 if payload["isStructural"] else 0
    if "closesWith" in payload:
        cmd.closes_with = payload["closesWith"] or None
    if "fields" in payload:
        cmd.fields = json.dumps(payload["fields"])
    if "handler" in payload:
        cmd.handler = payload["handler"] or None
    if "local" in payload:
        cmd.local = 1 if payload["local"] else 0
    if "enabled" in payload:
        cmd.enabled = 1 if payload["enabled"] else 0
    if "reviewedAt" in payload:
        cmd.reviewed_at = parse_iso_datetime(payload["reviewedAt"])
    if "categoryOrder" in payload:
        cmd.category_order = int(payload["categoryOrder"])
    if "commandOrder" in payload:
        cmd.command_order = int(payload["commandOrder"])

    db.commit()
    db.refresh(cmd)
    return {"success": True}


@router.get("/{cmd_id}/source")
def get_command_source(cmd_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Return the handler source code for a command."""
    import inspect

    cmd = db.get(models.WorkflowCommand, cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    from ..workflow.handlers.registry import get_handler
    h = get_handler(cmd.type)
    if h and h.get("handler_class"):
        try:
            source = inspect.getsource(h["handler_class"])
            return {"type": cmd.type, "source": source}
        except Exception:
            pass

    # Fallback: try emitter source
    emitter = h.get("emitter_handler")
    if emitter:
        return {"type": cmd.type, "source": f"# Emitter ({cmd.type})\n# Source not available via inspect", "fallback": True}

    return {"type": cmd.type, "source": None, "fallback": True}


@router.delete("/{cmd_id}")
def delete_command(cmd_id: int, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    cmd = db.get(models.WorkflowCommand, cmd_id)
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")
    if cmd.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete built-in command")
    db.delete(cmd)
    db.commit()
    return {"success": True}


def _analyze_command_recommendation(cmd_type: str, fields: list, is_container: bool, is_structural: bool) -> dict:
    """Smart recommendation for runtime configuration based on command schema."""
    field_names = {f.get("name") for f in fields}

    # Rule 1: containers / structural markers need no runtime
    if is_container:
        return {"needsRuntime": False, "handler": None, "local": False,
                "reason": "容器指令由 emitter 直接展开子节点，不需要 runtime", "confidence": "high"}
    if is_structural:
        return {"needsRuntime": False, "handler": None, "local": False,
                "reason": "结构标记仅用于语法闭合，不需要 runtime", "confidence": "high"}
    if cmd_type == "custom":
        return {"needsRuntime": False, "handler": None, "local": False,
                "reason": "自定义代码是 Python-only，不经过 extension", "confidence": "high"}

    # Rule 2: has script → executeJs
    if "script" in field_names:
        return {"needsRuntime": True, "handler": "executeJs", "local": False,
                "reason": "有 script 字段，需要浏览器执行 JS", "confidence": "high"}

    # Rule 3: has locator → page interaction (extension)
    if "locator" in field_names:
        handler_guess = None
        confidence = "medium"
        if cmd_type in ("click", "doubleClick", "rightClick", "clickByIndex", "clickIfExists"):
            handler_guess = "click"
            confidence = "high"
        elif cmd_type in ("input", "inputAndPressEnter", "clearInput"):
            handler_guess = "input" if cmd_type != "clearInput" else "clearInput"
            confidence = "high"
        elif cmd_type in ("getText", "getAttr", "getHtml", "getValue"):
            handler_guess = "extract"
            confidence = "high"
        elif cmd_type in ("scrollToBottom", "scrollToTop", "scrollOneScreen", "scrollIntoView", "scrollBy"):
            handler_guess = "scroll"
            confidence = "high"
        elif cmd_type == "hover":
            handler_guess = "hover"
            confidence = "high"
        elif cmd_type == "selectOption":
            handler_guess = "selectOption"
            confidence = "high"
        elif cmd_type in ("waitForElement", "waitForElementHide", "waitForText"):
            handler_guess = "wait"
            confidence = "medium"  # wait handler currently only sleeps
        else:
            handler_guess = cmd_type
            confidence = "low"
        return {"needsRuntime": True, "handler": handler_guess, "local": False,
                "reason": f"有 locator 字段，属于页面交互指令，推荐 handler={handler_guess}", "confidence": confidence}

    # Rule 4: openBrowser is backend-only (launches browser + extension)
    if cmd_type == "openBrowser":
        return {"needsRuntime": True, "handler": "openBrowser", "local": True,
                "reason": "openBrowser 由后端启动浏览器并加载扩展", "confidence": "high"}

    # Rule 5: known navigation commands → browser execution
    nav_types = ("closeBrowser", "navigate", "newTab", "goBack", "goForward", "refresh")
    if cmd_type in nav_types:
        handler_map = {"closeBrowser": "closeBrowser",
                       "navigate": "navigate", "newTab": "newTab", "goBack": "goBack",
                       "goForward": "goForward", "refresh": "refresh"}
        h = handler_map.get(cmd_type, cmd_type)
        return {"needsRuntime": True, "handler": h, "local": False,
                "reason": "页面导航类指令，需要浏览器执行", "confidence": "high"}

    # Rule 5: variable / data / output / network / AI / subflow → local=true
    local_keywords = {"varName", "name", "value", "listName", "targetVar", "step",
                      "message", "level", "dataExpr", "dataVar", "filePath", "format",
                      "method", "headers", "body", "appType", "inputs", "workflowId",
                      "resultExpr", "savePath", "fullPage"}
    if field_names & local_keywords or cmd_type in ("setVar", "log", "appendToList", "increment",
                                                      "stringConcat", "pushItem", "saveToFile",
                                                      "httpRequest", "callAiApp", "callWorkflow",
                                                      "return", "takeScreenshot", "keyCombo"):
        handler_guess = cmd_type
        return {"needsRuntime": True, "handler": handler_guess, "local": True,
                "reason": "后端变量/日志/文件/网络/AI/子流程操作，推荐 local=True 后端执行", "confidence": "high"}

    # Rule 6: fallback url field (unknown command) → assume browser navigation
    if "url" in field_names:
        return {"needsRuntime": True, "handler": cmd_type, "local": False,
                "reason": "包含 url 字段，疑似页面导航，建议浏览器执行", "confidence": "low"}

    # Rule 7: wait / sleep
    if cmd_type in ("sleep", "waitForLoad", "waitForUrl") or "seconds" in field_names or "timeout" in field_names:
        return {"needsRuntime": True, "handler": "wait", "local": False,
                "reason": "等待/超时类指令，推荐 wait handler", "confidence": "medium"}

    # Fallback
    return {"needsRuntime": False, "handler": None, "local": False,
            "reason": "未识别到明确的 runtime 匹配规则，建议人工判定", "confidence": "low"}


@router.post("/analyze")
def analyze_command(payload: dict[str, Any], user=Depends(auth.get_current_user)):
    """Smart analysis: recommend runtime config + run consistency checks for a single command."""
    cmd_type = payload.get("type", "")
    fields = payload.get("fields", [])
    is_container = payload.get("isContainer", False)
    is_structural = payload.get("isStructural", False)

    rec = _analyze_command_recommendation(cmd_type, fields, is_container, is_structural)

    # Consistency checks against current config
    issues = []
    current_has_runtime = payload.get("hasRuntime", False)
    current_handler = payload.get("handler", "")
    current_local = payload.get("local", False)

    if rec["needsRuntime"] and not current_has_runtime:
        issues.append(f"推荐启用 runtime（{rec['reason']}）")
    if not rec["needsRuntime"] and current_has_runtime:
        issues.append(f"推荐禁用 runtime（{rec['reason']}）")
    if rec["needsRuntime"] and current_has_runtime and rec.get("handler") and rec["handler"] != current_handler:
        issues.append(f"handler 不匹配：推荐 '{rec['handler']}'，当前 '{current_handler}'")
    if rec.get("local") != current_local:
        issues.append(f"local 建议：推荐 {'本地执行' if rec['local'] else '浏览器执行'}，当前 {'本地执行' if current_local else '浏览器执行'}")

    return {
        "recommendation": rec,
        "issues": issues,
        "passed": len(issues) == 0,
    }


@router.get("/handlers")
def list_handlers(user=Depends(auth.get_current_user)):
    """Return available content.js handler names for dropdown selection."""
    handlers = sorted(extract_js_handler_names())
    return {"handlers": handlers}


@router.get("/export/csv")
def export_csv(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    rows = db.query(models.WorkflowCommand).order_by(
        models.WorkflowCommand.category_order,
        models.WorkflowCommand.command_order,
    ).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "分类", "指令类型", "显示名称", "是否容器", "是否分支", "是否结构标记",
        "参数定义(JSON)", "是否内置", "状态", "图标", "图标颜色", "背景颜色",
        "分类排序", "指令排序",
    ])
    for r in rows:
        writer.writerow([
            r.category,
            r.type,
            r.label,
            "是" if r.is_container else "否",
            "是" if r.is_branch else "否",
            "是" if r.is_structural else "否",
            r.fields or "[]",
            "是" if r.is_builtin else "否",
            "启用" if r.enabled else "禁用",
            r.icon,
            r.icon_color,
            r.bg_color,
            r.category_order,
            r.command_order,
        ])

    buf.seek(0)
    filename = f"workflow_commands_{models.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/enable-all")
def enable_all_commands(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """启用所有指令（内置 + 自定义）。"""
    count = db.query(models.WorkflowCommand).filter(models.WorkflowCommand.enabled == 0).count()
    db.query(models.WorkflowCommand).update({"enabled": 1})
    db.commit()
    return {"success": True, "count": count}


# ── Command definition JSON editing ──────────────────────────

import os as _os
from pathlib import Path as _Path

_COMMANDS_DIR = _Path(__file__).resolve().parent.parent.parent.parent / "commands"


@router.get("/definitions")
def list_definitions(user=Depends(auth.get_current_user)):
    """List all command definition JSON files."""
    if not _COMMANDS_DIR.exists():
        return []
    result = []
    for fp in sorted(_COMMANDS_DIR.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        data["_file"] = fp.name
        result.append(data)
    return result


@router.get("/definitions/{type_name}")
def get_definition(type_name: str, user=Depends(auth.get_current_user)):
    """Get a single command definition JSON."""
    fp = _COMMANDS_DIR / f"{type_name}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"Definition '{type_name}' not found")
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


@router.put("/definitions/{type_name}")
def save_definition(type_name: str, payload: dict, user=Depends(auth.get_current_user)):
    """Save a command definition JSON. Creates if not exists."""
    fp = _COMMANDS_DIR / f"{type_name}.json"
    _os.makedirs(_COMMANDS_DIR, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"success": True, "file": fp.name}


@router.delete("/definitions/{type_name}")
def delete_definition(type_name: str, user=Depends(auth.get_current_user)):
    """Delete a command definition JSON and its handler file."""
    fp = _COMMANDS_DIR / f"{type_name}.json"
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"Definition '{type_name}' not found")
    fp.unlink()
    # Also delete handler file if it exists
    hfp = _Path(__file__).resolve().parent.parent.parent.parent / "src" / "runtime" / "commands" / "backend_commands" / f"{type_name}.py"
    if hfp.exists():
        hfp.unlink()
    return {"success": True}


@router.post("/definitions/build")
def build_definitions(user=Depends(auth.get_current_user)):
    """Run generate_commands.py and build_content_js.py."""
    import subprocess, sys
    root = _COMMANDS_DIR.parent
    results = []
    for script in ["scripts/generate_commands.py", "scripts/build_content_js.py", "scripts/build_background_js.py"]:
        sp = subprocess.run(
            [sys.executable, str(root / script)],
            capture_output=True, text=True, cwd=str(root),
        )
        results.append({
            "script": script,
            "returncode": sp.returncode,
            "stdout": sp.stdout[-500:],
            "stderr": sp.stderr[-500:],
        })
    all_ok = all(r["returncode"] == 0 for r in results)
    return {"success": all_ok, "results": results}


_HANDLERS_BASE_DIR = _Path(__file__).resolve().parent.parent.parent.parent / "src" / "runtime" / "commands"

_RUNTIME_DIRS = ["backend_commands", "extension_commands", "control_commands"]


@router.get("/definitions/{type_name}/source")
def get_handler_source(type_name: str, user=Depends(auth.get_current_user)):
    """Return the saved Python handler source for a new-system command."""
    for sub in _RUNTIME_DIRS:
        fp = _HANDLERS_BASE_DIR / sub / f"{type_name}.py"
        if fp.exists():
            return {"type": type_name, "code": fp.read_text(encoding="utf-8"), "exists": True}
    return {"type": type_name, "code": "", "exists": False}


@router.post("/definitions/{type_name}/save-handler")
def save_handler_code(type_name: str, payload: dict, user=Depends(auth.get_current_user)):
    """Save AI-generated Python handler code for a new-system command."""
    code = payload.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    try:
        compile(code, f"{type_name}.py", "exec")
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax error: {e}")

    # Determine target directory from the definition's runtime field
    def_fp = _COMMANDS_DIR / f"{type_name}.json"
    if def_fp.exists():
        with open(def_fp, encoding="utf-8") as f2:
            definition = json.load(f2)
        runtime = definition.get("runtime", "backend")
    else:
        runtime = "backend"
    target_dir = _HANDLERS_BASE_DIR / f"{runtime}_commands"
    target_dir.mkdir(parents=True, exist_ok=True)
    fp = target_dir / f"{type_name}.py"
    with open(fp, "w", encoding="utf-8") as f:
        f.write(code)
    return {"success": True, "file": fp.name}


@router.get("/definitions/{type_name}/js-source")
def get_js_handler_source(type_name: str, user=Depends(auth.get_current_user)):
    """Return the JS handler source for an extension command."""
    def_fp = _COMMANDS_DIR / f"{type_name}.json"
    if not def_fp.exists():
        return {"type": type_name, "code": "", "exists": False}
    with open(def_fp, encoding="utf-8") as f2:
        definition = json.load(f2)
    handler = definition.get("handler", {})
    source_path = handler.get("source", "")
    if not source_path:
        return {"type": type_name, "code": "", "exists": False}
    fp = _Path(__file__).resolve().parent.parent.parent.parent / source_path
    if not fp.exists():
        return {"type": type_name, "code": "", "exists": False, "path": source_path}
    return {"type": type_name, "code": fp.read_text(encoding="utf-8"), "exists": True, "path": source_path}


@router.post("/definitions/{type_name}/save-js-handler")
def save_js_handler_code(type_name: str, payload: dict, user=Depends(auth.get_current_user)):
    """Save JS handler code for an extension command."""
    code = payload.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="code is required")
    def_fp = _COMMANDS_DIR / f"{type_name}.json"
    if not def_fp.exists():
        raise HTTPException(status_code=404, detail=f"Definition '{type_name}' not found")
    with open(def_fp, encoding="utf-8") as f2:
        definition = json.load(f2)
    handler = definition.get("handler", {})
    source_path = handler.get("source", "")
    if not source_path:
        raise HTTPException(status_code=400, detail="handler.source not defined")
    fp = _Path(__file__).resolve().parent.parent.parent.parent / source_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(code, encoding="utf-8")
    return {"success": True, "file": fp.name}


# ─── Command Categories (for new command definition system) ─────────────

cat_router = APIRouter(prefix="/api/command-categories", tags=["command-categories"])


@cat_router.get("")
def list_categories(db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """List all command categories, ordered by sort_order."""
    rows = db.query(models.CommandCategory).order_by(models.CommandCategory.sort_order).all()
    return [{
        "id": r.id,
        "slug": r.slug,
        "name": r.name,
        "icon": r.icon or "fa-folder",
        "sortOrder": r.sort_order,
        "description": r.description or "",
    } for r in rows]


@cat_router.post("")
def create_category(payload: dict, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Create a new command category."""
    slug = (payload.get("slug") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    if not slug or not name:
        raise HTTPException(status_code=400, detail="slug and name are required")
    if db.query(models.CommandCategory).filter(models.CommandCategory.slug == slug).first():
        raise HTTPException(status_code=409, detail=f"Category '{slug}' already exists")
    row = models.CommandCategory(
        slug=slug,
        name=name,
        icon=payload.get("icon", "fa-folder"),
        sort_order=payload.get("sortOrder", 0),
        description=payload.get("description", ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": row.id, "slug": row.slug}


@cat_router.put("/{slug}")
def update_category(slug: str, payload: dict, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Update a command category."""
    row = db.query(models.CommandCategory).filter(models.CommandCategory.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Category '{slug}' not found")
    if "name" in payload:
        row.name = payload["name"].strip()
    if "icon" in payload:
        row.icon = payload["icon"]
    if "sortOrder" in payload:
        row.sort_order = payload["sortOrder"]
    if "description" in payload:
        row.description = payload["description"]
    db.commit()
    return {"ok": True}


@cat_router.delete("/{slug}")
def delete_category(slug: str, db: Session = Depends(get_db), user=Depends(auth.get_current_user)):
    """Delete a command category."""
    row = db.query(models.CommandCategory).filter(models.CommandCategory.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Category '{slug}' not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ─── Value Types ─────────────────────────────────────────────


@router.get("/value-types")
def get_value_types(user=Depends(auth.get_current_user)):
    """Return project-level value type definitions."""
    fp = _COMMANDS_DIR / "value_types.json"
    if not fp.exists():
        return {"types": {}}
    with open(fp, encoding="utf-8") as f:
        return json.load(f)
