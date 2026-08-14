"""桌面控件统一引用 — Win32/UIA 自动路由共用工具。

「自动选择」指令（findWindowAuto/clickControlAuto/inputControlAuto/pickElementAuto）
把目标控件表示为统一引用 dict，消费时按 desktop_ref 标记路由到 Win32 或 UIA 通道；
同时兼容旧指令产物（findWindowWin32 存的 int hwnd、findWindowUia 存的 UIA dict）。
"""


def make_win32_ref(hwnd: int, title: str = "", class_name: str = "", rect=None) -> dict:
    """构造 Win32 通道的统一引用。"""
    return {
        "desktop_ref": "win32",
        "hwnd": int(hwnd),
        "title": title or "",
        "class_name": class_name or "",
        "rect": rect or {},
    }


def make_uia_ref(elem: dict) -> dict:
    """构造 UIA 通道的统一引用（elem 为 _uia 返回的元素 dict，含运行时 _uia_ctrl）。"""
    return {
        "desktop_ref": "uia",
        "name": (elem or {}).get("name", ""),
        "class_name": (elem or {}).get("class_name", ""),
        "control_type": (elem or {}).get("control_type", ""),
        "automation_id": (elem or {}).get("automation_id", ""),
        "_uia_ctrl": (elem or {}).get("_uia_ctrl"),
    }


def resolve_target(value):
    """识别目标控件引用，返回 (channel, target)。

    channel: "win32" → target 为 int hwnd
             "uia"   → target 为 UIA 元素 dict
             None    → target 为 None（无法识别）
    兼容：int（旧 findWindowWin32/pickFromPathWin32 产物）、
         UIA dict（旧 findWindowUia/pickElementUia 产物）、
         统一引用 dict（本工具 make_*_ref 产物）。
    """
    if isinstance(value, int):
        return "win32", value
    if isinstance(value, dict):
        ref = value.get("desktop_ref")
        if ref == "win32":
            return "win32", value.get("hwnd")
        if ref == "uia":
            # 返回整个引用 dict（含 _uia_ctrl）—— _uia.click_element/set_text
            # 接受 dict 形态（_to_uia_control 内部取 _uia_ctrl）。
            return "uia", value
        # 兼容旧格式
        if "_uia_ctrl" in value or ("control_type" in value and "hwnd" not in value):
            return "uia", value
        if "hwnd" in value:
            return "win32", value.get("hwnd")
    return None, None
