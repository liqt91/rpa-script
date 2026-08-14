"""
T1 桌面指令参数 schema 校验（纯静态，无需真机）。

覆盖 12 个 Win32 + 4 个 UIA 桌面指令：注册存在、runtime=backend、字段完整、类型合法。
见 docs/指令全量测试方案-20260814.md §4.1。
"""
from src.runtime.workflow.handlers.registry import build_command_registry

DESKTOP_CMDS = [
    # 自动选择 (4)
    "clickControlAuto", "findWindowAuto", "inputControlAuto", "pickElementAuto",
    # Win32 (15)
    "clickControlWin32", "clickMenuWin32", "closeWindowWin32", "findChildWin32",
    "findParentWin32", "findSiblingWin32", "findWindowWin32", "inputControlWin32",
    "mouseClickWin32", "openAppWin32", "pickFromPathWin32", "screenshotWindowWin32",
    "sendKeyWin32", "waitWindowWin32", "waitWin32",
    # UIA (4)
    "clickElementUia", "findWindowUia", "inputElementUia", "pickElementUia",
]

VALID_TYPES = {
    "str-var", "any-input", "string", "text", "select",
    "element", "number", "boolean", "code",
}


def test_all_desktop_commands_registered_as_backend():
    reg = build_command_registry()
    for cmd in DESKTOP_CMDS:
        assert cmd in reg, f"{cmd} 未注册"
        ext = reg[cmd].get("runtimes", {}).get("extension") or {}
        assert ext.get("local") is True, f"{cmd} 应为本地后端执行(local=True)，实际 {ext}"


def test_desktop_command_fields_complete():
    reg = build_command_registry()
    for cmd in DESKTOP_CMDS:
        fields = reg[cmd]["fields"]
        assert isinstance(fields, list) and fields, f"{cmd} 无参数定义"
        names = [f["name"] for f in fields]
        assert len(names) == len(set(names)), f"{cmd} 参数名重复: {names}"
        for f in fields:
            assert f.get("name") and f.get("label"), f"{cmd} 参数缺 name/label: {f}"
            assert f.get("type") in VALID_TYPES, \
                f"{cmd} 参数 {f['name']} 类型非法: {f.get('type')}"
            if f.get("type") in ("select", "select"):
                assert f.get("options"), f"{cmd} 参数 {f['name']} 为 select 但无 options"
