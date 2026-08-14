"""
T1 指令热重载测试：/api/commands/reload 的核心逻辑（reload_command_runtime）。

验证重新导入指令模块后 registry / LOCAL_HANDLERS / new_catalog / DB 同步一致，
且幂等可重复调用。不经过 HTTP，直接调用核心函数。
"""
from src.runtime.workflow.command_reload import reload_command_runtime

# 桌面指令抽查（含自动选择与新指令）
DESKTOP_CMDS = [
    "openAppWin32", "waitWindowWin32", "findWindowAuto", "findWindowWin32",
    "findWindowUia", "findParentWin32", "findSiblingWin32", "findChildWin32",
    "pickElementAuto", "pickFromPathWin32", "pickElementUia",
    "clickControlAuto", "clickControlWin32", "clickElementUia",
    "inputControlAuto", "inputControlWin32", "inputElementUia",
    "sendKeyWin32", "mouseClickWin32", "clickMenuWin32", "waitWin32",
    "screenshotWindowWin32", "closeWindowWin32",
]


def test_reload_populates_registry_and_local_handlers():
    from src.runtime.workflow.handlers.registry import get_all_handlers
    from src.runtime.workflow.extension_runner import LOCAL_HANDLERS

    before_handlers = len(get_all_handlers())
    result = reload_command_runtime()

    assert result["success"] is True, result
    assert result["handlers"] >= before_handlers, f"重载后指令数减少: {result}"
    assert result["local_handlers"] > 0, f"LOCAL_HANDLERS 为空: {result}"

    reg = get_all_handlers()
    for cmd in DESKTOP_CMDS:
        assert cmd in reg, f"重载后缺少指令 {cmd}"
        assert reg[cmd]["category"] == "桌面操作", f"{cmd} 分类错误: {reg[cmd]['category']}"

    for cmd in ("findWindowAuto", "clickControlAuto", "inputControlAuto",
                "pickElementAuto", "waitWindowWin32", "mouseClickWin32",
                "screenshotWindowWin32"):
        assert cmd in LOCAL_HANDLERS, f"LOCAL_HANDLERS 缺少 {cmd}"


def test_reload_is_idempotent():
    from src.runtime.workflow.handlers.registry import get_all_handlers

    n1 = len(get_all_handlers())
    r1 = reload_command_runtime()
    r2 = reload_command_runtime()
    assert r2["handlers"] == r1["handlers"] == n1, f"重载后数量漂移: {r1} {r2}"


def test_reload_updates_new_catalog_categories():
    from src.runtime.workflow.new_catalog import load_new_catalog

    reload_command_runtime()
    cat = load_new_catalog()
    assert "桌面操作" in cat["categories"], f"分类缺失: {cat['categories']}"
    desktop = cat["commands"].get("桌面操作", [])
    assert len(desktop) == 23, f"桌面指令数异常: {len(desktop)}"
    orders = [c["commandOrder"] for c in desktop]
    assert orders == sorted(orders), f"commandOrder 未按序: {orders}"


def test_reload_with_db_syncs_workflow_commands(db_session):
    """带 DB 时同步 WorkflowCommand：桌面指令记录存在且分类为「桌面操作」。"""
    from src.repo import models

    reload_command_runtime(db=db_session)
    rows = (
        db_session.query(models.WorkflowCommand)
        .filter(models.WorkflowCommand.cmd.in_(DESKTOP_CMDS))
        .all()
    )
    cmds = {r.cmd for r in rows}
    assert cmds == set(DESKTOP_CMDS), f"DB 缺少桌面指令: {set(DESKTOP_CMDS) - cmds}"
    for r in rows:
        assert r.category == "桌面操作", f"{r.cmd} DB 分类错误: {r.category}"
        assert r.is_builtin, f"{r.cmd} 应为内置指令"


def test_reload_endpoint_via_http(client, auth_headers):
    """HTTP 级：POST /api/commands/reload 返回重载统计，registry 完整。"""
    r = client.post("/api/commands/reload", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True, data
    assert data.get("handlers", 0) >= 60, f"重载后指令数异常: {data}"
    assert data.get("local_handlers", 0) > 0, f"LOCAL_HANDLERS 为空: {data}"
    assert data.get("db_synced") is True, f"应同步 DB: {data}"


def test_param_options_api_roundtrip(client, auth_headers):
    """参数模板已并入 value_types.json（paramTemplates 段）：/value-types 返回含模板，
    PUT 后保留；$ref 在指令 definitions 中正确展开。"""
    r = client.get("/api/commands/value-types", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "paramTemplates" in data, f"缺 paramTemplates: {list(data)}"
    tmpl = data["paramTemplates"]
    assert "searchMode" in tmpl and "clickType" in tmpl and "method" in tmpl, \
        f"模板缺失: {list(tmpl)}"
    assert "paramTypes" in data and "str-var" in data["paramTypes"], \
        "str-var 应为正式类型"
    assert "legacyMap" not in data, "legacyMap 应已删除"

    # $ref 展开：findWindowAuto 的 searchMode/method 来自 paramTemplates
    d = client.get("/api/commands/definitions/findWindowAuto", headers=auth_headers)
    assert d.status_code == 200, d.text
    params = d.json().get("params", [])
    names = {p.get("name") for p in params}
    assert "searchMode" in names and "method" in names, f"findWindowAuto 参数异常: {names}"
    sm = next(p for p in params if p.get("name") == "searchMode")
    assert len(sm.get("options", [])) == 3, f"searchMode 应展开 3 项: {sm}"
    assert "$ref" not in sm, f"$ref 未展开: {sm}"

    # value-types PUT 保留 paramTemplates 且往返一致
    r2 = client.put("/api/commands/value-types", headers=auth_headers, json=data)
    assert r2.status_code == 200, r2.text
    r3 = client.get("/api/commands/value-types", headers=auth_headers)
    assert r3.json() == data, "PUT 后 GET 不一致"
