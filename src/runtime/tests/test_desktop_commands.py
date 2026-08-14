"""
T3 桌面指令自动化（真实 Windows 桌面，目标：记事本 notepad.exe）。

走真实 handler 代码（run_handler），在真机上执行 Win32/UIA 调用并断言结果。
每个用例独立启动记事本并在 finally 关闭，互不干扰。
见 docs/指令全量测试方案-20260814.md §6。
"""
import json
import time

import pytest

from .handler_test_utils import make_runner, run_handler

NOTE_FUZZY = "记事本"   # 中文系统记事本标题「无标题 - 记事本」模糊匹配


@pytest.fixture(scope="module", autouse=True)
def _clean_stray_notepads():
    """模块前后清理残留记事本进程，避免模糊查找命中旧窗口（真机测试隔离）。"""
    import subprocess
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"],
                   capture_output=True, timeout=10)
    time.sleep(0.5)
    yield
    subprocess.run(["taskkill", "/f", "/im", "notepad.exe"],
                   capture_output=True, timeout=10)


def _last_result(r):
    """取最近一条结果的 result dict（error 也在里面）。"""
    if not r.results:
        return {}
    last = r.results[-1]
    return last.get("result", {}) if isinstance(last, dict) else {}


async def _open_notepad(result_var="hwnd"):
    r = make_runner()
    await run_handler("openAppWin32", {"app": "notepad", "resultVar": result_var}, r)
    assert result_var in r.vars, f"openAppWin32 未写入变量 {result_var}: {_last_result(r)}"
    return r


async def _find_notepad(r, retries=15):
    """模糊查找记事本窗口，返回 (result, runner)。result.window.hwnd 为窗口句柄。"""
    for _ in range(retries):
        rr = make_runner()
        await run_handler("findWindowWin32",
                          {"searchMode": "fuzzy", "windowTitle": NOTE_FUZZY,
                           "autoActivate": True, "resultVar": "win"},
                          rr)
        res = _last_result(rr)
        if res.get("found"):
            return res, rr
        time.sleep(0.4)
    raise AssertionError(f"findWindowWin32 未找到记事本: {_last_result(rr)}")


def _window_hwnd(res):
    """findWindowWin32 结果的窗口句柄（嵌套在 result.window.hwnd）。"""
    win = res.get("window") or {}
    return win.get("hwnd", 0)


async def _close(r, hwnd_var="hwnd"):
    if hwnd_var in r.vars:
        try:
            await run_handler("closeWindowWin32", {"parentWindow": hwnd_var}, r)
        except Exception:
            pass


# ── Win32 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_open_app_notepad():
    r = await _open_notepad()
    try:
        hwnd = r.vars["hwnd"]
        assert isinstance(hwnd, int) and hwnd > 0, f"hwnd 非法: {hwnd}"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_find_window_fuzzy():
    r = await _open_notepad()
    try:
        res, _ = await _find_notepad(r)
        assert _window_hwnd(res) > 0
        assert "记事本" in res.get("log", ""), res
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_find_child_edit_and_input():
    r = await _open_notepad()
    try:
        win_res, _ = await _find_notepad(r)
        r.vars["win"] = _window_hwnd(win_res)
        await run_handler("findChildWin32",
                          {"parentWindow": "win", "classFilter": "Edit",
                           "matchIndex": 1, "resultVar": "edit"}, r)
        res = _last_result(r)
        assert res.get("found"), f"findChildWin32 未找到 Edit: {res}"
        edit_hwnd = res.get("hwnd")
        assert edit_hwnd, f"findChildWin32 无 hwnd: {res}"
        r.vars["edit"] = edit_hwnd
        await run_handler("inputControlWin32",
                          {"targetHwnd": "edit", "text": "RPA桌面自动化测试"}, r)
        in_res = _last_result(r)
        assert not in_res.get("error"), f"inputControlWin32 失败: {in_res}"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_send_key_ctrl_a():
    r = await _open_notepad()
    try:
        win_res, _ = await _find_notepad(r)
        r.vars["win"] = _window_hwnd(win_res)
        await run_handler("sendKeyWin32", {"key": "a", "modifiers": "Ctrl"}, r)
        res = _last_result(r)
        assert not res.get("error"), f"sendKeyWin32 失败: {res}"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_click_menu_exit_dialog_then_close():
    """clickMenuWin32 文件→退出：菜单点击成功 → 主窗口关闭（D6 实为保存确认框或残留窗口误判，
    非缺陷）。用具体 hwnd 的 window_exists 验证。"""
    from src.runtime.commands.desktop_commands import _win32
    r = await _open_notepad()
    try:
        win_res, _ = await _find_notepad(r)
        win_hwnd = _window_hwnd(win_res)
        r.vars["win"] = win_hwnd
        # 兼容 "->" 与 "→" 两种分隔符（D3 已修）
        await run_handler("clickMenuWin32", {"parentWindow": "win", "menuPath": "文件→退出"}, r)
        res = _last_result(r)
        assert res.get("found") is not False, f"clickMenuWin32 未找到菜单: {res}"
        assert not res.get("error"), f"clickMenuWin32 失败: {res}"
        # 若弹「是否保存」确认框 → 全局 Escape（sendKeyWin32 全局按键，确认框有焦点）
        time.sleep(0.6)
        await run_handler("sendKeyWin32", {"key": "Escape"}, r)
        # 轮询：具体主窗口必须消失（避免模糊搜索命中残留窗口）
        for _ in range(10):
            if not _win32.window_exists(win_hwnd):
                break
            time.sleep(0.5)
        else:
            pytest.fail("点击「文件→退出」并 Escape 后主窗口未关闭")
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_wait_fixed():
    r = make_runner()
    await run_handler("waitWin32", {"mode": "fixed", "seconds": 0.3}, r)
    assert not _last_result(r).get("error")


@pytest.mark.asyncio
async def test_close_window():
    r = await _open_notepad()
    win_res, _ = await _find_notepad(r)
    r.vars["win"] = _window_hwnd(win_res)
    await run_handler("closeWindowWin32", {"parentWindow": "win"}, r)
    res = _last_result(r)
    assert not res.get("error"), f"closeWindowWin32 失败: {res}"


# ── UIA ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_uia_find_window():
    r = await _open_notepad()
    try:
        await run_handler("findWindowUia",
                          {"windowTitle": NOTE_FUZZY, "searchMode": "fuzzy",
                           "resultVar": "uiaWin"}, r)
        res = _last_result(r)
        assert res.get("found"), f"findWindowUia 未找到记事本: {res}"
        assert "uiaWin" in r.vars, "findWindowUia 未写入 resultVar"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_uia_pick_click_input_edit():
    """合成元素库元素（记事本 Edit 的 UIA 路径）→ pickElementUia → clickElementUia → inputElementUia。

    依赖 D5 修复（_uia.find_child_by_enum 兜底：uiautomation 条件搜索对 Win11 记事本失效）。
    """
    from src.repo import models
    db = models.SessionLocal()
    try:
        el = models.WorkflowElement(
            workflow_id=1, name="记事本编辑框-测试", element_type="uia", element_kind="plain",
            attributes=json.dumps({
                "path": [
                    {"name": NOTE_FUZZY, "control_type": "WindowControl"},
                    {"class_name": "Edit", "control_type": "EditControl"},
                ],
                "uia_target_index": 1,
            }, ensure_ascii=False),
        )
        db.add(el)
        db.commit()
    finally:
        db.close()
    r = await _open_notepad()
    try:
        await _find_notepad(r)  # 确保窗口在前台
        await run_handler("pickElementUia",
                          {"elementName": "记事本编辑框-测试", "resultVar": "edit"}, r)
        res = _last_result(r)
        assert res.get("found"), f"pickElementUia 未找到 Edit: {res}"
        assert "edit" in r.vars, "pickElementUia 未写入 resultVar"
        await run_handler("clickElementUia", {"targetElement": "edit"}, r)
        assert not _last_result(r).get("error"), f"clickElementUia 失败: {_last_result(r)}"
        await run_handler("inputElementUia", {"targetElement": "edit", "text": "UIA输入测试"}, r)
        assert not _last_result(r).get("error"), f"inputElementUia 失败: {_last_result(r)}"
    finally:
        await _close(r)
        db = models.SessionLocal()
        try:
            db.query(models.WorkflowElement).filter_by(name="记事本编辑框-测试").delete()
            db.commit()
        finally:
            db.close()


# ── 新指令（2026-08-14 补充）──

@pytest.mark.asyncio
async def test_wait_window_appears():
    """waitWindowWin32：启动记事本后等待窗口出现，返回 hwnd。"""
    r = await _open_notepad()
    try:
        await run_handler("waitWindowWin32",
                          {"windowTitle": NOTE_FUZZY, "timeout": 10, "resultVar": "ww"}, r)
        res = _last_result(r)
        assert res.get("found"), f"waitWindowWin32 未等到窗口: {res}"
        assert res.get("hwnd", 0) > 0, f"waitWindowWin32 hwnd 非法: {res}"
        assert "ww" in r.vars, "waitWindowWin32 未写入 resultVar"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_wait_window_timeout_not_found():
    """waitWindowWin32 超时：不存在的窗口返回 found=False（软结果，不抛错）。"""
    r = make_runner()
    await run_handler("waitWindowWin32",
                      {"windowTitle": "不存在的窗口XYZ-自动化测试", "timeout": 1}, r)
    res = _last_result(r)
    assert res.get("found") is False, f"应返回 found=False: {res}"


@pytest.mark.asyncio
async def test_screenshot_window():
    """screenshotWindowWin32：截图记事本窗口保存 PNG，文件存在且非空。"""
    import os
    r = await _open_notepad()
    shot_path = os.path.join(os.environ.get("TEMP", "."), "rpa_notepad_shot.png")
    try:
        res, rr = await _find_notepad(r)
        hwnd = _window_hwnd(res)
        assert hwnd > 0
        rr.vars["win"] = hwnd
        await run_handler("screenshotWindowWin32",
                          {"parentWindow": "win", "savePath": shot_path, "resultVar": "sp"}, rr)
        sres = _last_result(rr)
        assert sres.get("saved"), f"screenshotWindowWin32 失败: {sres}"
        assert os.path.exists(shot_path), f"截图文件不存在: {shot_path}"
        assert os.path.getsize(shot_path) > 0, f"截图文件为空: {shot_path}"
    finally:
        await _close(r)
        if os.path.exists(shot_path):
            os.remove(shot_path)


@pytest.mark.asyncio
async def test_mouse_click_relative_window():
    """mouseClickWin32：相对窗口客户区坐标点击记事本编辑区（单击无副作用）。"""
    r = await _open_notepad()
    try:
        res, rr = await _find_notepad(r)
        hwnd = _window_hwnd(res)
        assert hwnd > 0
        rr.vars["win"] = hwnd
        await run_handler("mouseClickWin32",
                          {"x": 200, "y": 100, "windowHwnd": "win",
                           "clickType": "single", "resultVar": "pos"}, rr)
        mres = _last_result(rr)
        assert mres.get("clicked"), f"mouseClickWin32 失败: {mres}"
        assert isinstance(mres.get("x"), int) and isinstance(mres.get("y"), int), \
            f"相对坐标换算异常: {mres}"
        assert "pos" in rr.vars, "mouseClickWin32 未写入 resultVar"
        # 换算后的屏幕坐标应落在虚拟屏内（多显示器副屏坐标可能为负，用范围校验）
        import ctypes
        vx = ctypes.windll.user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vy = ctypes.windll.user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
        vw = ctypes.windll.user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        vh = ctypes.windll.user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
        assert vx <= mres["x"] < vx + vw, f"x 超出虚拟屏: {mres}"
        assert vy <= mres["y"] < vy + vh, f"y 超出虚拟屏: {mres}"
    finally:
        await _close(r)


# ── 自动选择指令（Win32/UIA 合并，2026-08-14）──

@pytest.mark.asyncio
async def test_auto_find_window():
    """findWindowAuto：自动通道查找记事本窗口，返回统一引用。"""
    r = await _open_notepad()
    try:
        await run_handler("findWindowAuto",
                          {"windowTitle": NOTE_FUZZY, "method": "auto", "resultVar": "win"}, r)
        res = _last_result(r)
        assert res.get("found"), f"findWindowAuto 未找到窗口: {res}"
        assert res.get("via") in ("uia", "win32"), f"via 异常: {res}"
        ref = r.vars.get("win")
        assert isinstance(ref, dict) and ref.get("desktop_ref") in ("uia", "win32"), \
            f"统一引用异常: {ref}"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_auto_click_input_win32_channel():
    """clickControlAuto/inputControlAuto：兼容旧 findWindowWin32 的 int hwnd（win32 通道）。"""
    r = await _open_notepad()
    try:
        res, rr = await _find_notepad(r)
        hwnd = _window_hwnd(res)
        assert hwnd > 0
        rr.vars["win"] = hwnd  # 旧格式：int hwnd
        await run_handler("clickControlAuto", {"targetControl": "win"}, rr)
        cres = _last_result(rr)
        assert cres.get("clicked"), f"clickControlAuto(win32) 失败: {cres}"
        assert cres.get("via") == "win32"
        # 输入到 Edit：findChildWin32 拿 Edit hwnd，再走 Auto 输入（win32 通道）
        await run_handler("findChildWin32",
                          {"parentWindow": "win", "classFilter": "Edit",
                           "matchIndex": 1, "resultVar": "edit"}, rr)
        edit_res = _last_result(rr)
        assert edit_res.get("found"), f"findChildWin32 未找到 Edit: {edit_res}"
        edit_hwnd = edit_res.get("hwnd")
        rr.vars["edit"] = edit_hwnd
        await run_handler("inputControlAuto", {"targetControl": "edit", "text": "自动输入测试"}, rr)
        ires = _last_result(rr)
        assert ires.get("via") == "win32", f"应走 win32 通道: {ires}"
        assert not ires.get("error"), f"inputControlAuto(win32) 失败: {ires}"
    finally:
        await _close(r)


@pytest.mark.asyncio
async def test_auto_pick_and_click_input_uia_channel():
    """pickElementAuto + clickControlAuto + inputControlAuto：UIA 元素自动路由（uia 通道）。"""
    from src.repo import models
    db = models.SessionLocal()
    try:
        el = models.WorkflowElement(
            workflow_id=1, name="记事本编辑框-自动测试", element_type="uia", element_kind="plain",
            attributes=json.dumps({
                "path": [
                    {"name": NOTE_FUZZY, "control_type": "WindowControl"},
                    {"class_name": "Edit", "control_type": "EditControl"},
                ],
                "uia_target_index": 1,
            }, ensure_ascii=False),
        )
        db.add(el)
        db.commit()
    finally:
        db.close()
    r = await _open_notepad()
    try:
        await _find_notepad(r)  # 确保窗口在前台
        await run_handler("pickElementAuto",
                          {"elementName": "记事本编辑框-自动测试", "levelIndex": -1, "resultVar": "edit"}, r)
        pres = _last_result(r)
        assert pres.get("found"), f"pickElementAuto(uia) 未找到: {pres}"
        assert pres.get("via") == "uia", f"应走 uia 通道: {pres}"
        ref = r.vars.get("edit")
        assert isinstance(ref, dict) and ref.get("desktop_ref") == "uia"
        await run_handler("clickControlAuto", {"targetControl": "edit"}, r)
        cres = _last_result(r)
        assert cres.get("clicked") and cres.get("via") == "uia", f"clickControlAuto(uia) 失败: {cres}"
        await run_handler("inputControlAuto", {"targetControl": "edit", "text": "UIA自动输入"}, r)
        ires = _last_result(r)
        assert ires.get("via") == "uia", f"应走 uia 通道: {ires}"
        assert not ires.get("error"), f"inputControlAuto(uia) 失败: {ires}"
    finally:
        await _close(r)
        db = models.SessionLocal()
        try:
            db.query(models.WorkflowElement).filter_by(name="记事本编辑框-自动测试").delete()
            db.commit()
        finally:
            db.close()


@pytest.mark.asyncio
async def test_auto_pick_element_win32_channel():
    """pickElementAuto：win32 path 元素自动路由（win32 通道）。"""
    from src.repo import models
    r = await _open_notepad()
    db = models.SessionLocal()
    try:
        res, rr = await _find_notepad(r)
        hwnd = _window_hwnd(res)
        assert hwnd > 0
        rr.vars["win"] = hwnd
        await run_handler("findChildWin32",
                          {"parentWindow": "win", "classFilter": "Edit",
                           "matchIndex": 1, "resultVar": "edit"}, rr)
        edit_hwnd = _last_result(rr).get("hwnd")
        assert edit_hwnd, "未找到 Edit"
        el = models.WorkflowElement(
            workflow_id=1, name="记事本Edit-自动路径", element_type="win32", element_kind="plain",
            attributes=json.dumps({
                "path": [
                    {"hwnd": hwnd, "class_name": "Notepad", "title": NOTE_FUZZY, "rect": {}},
                    {"hwnd": edit_hwnd, "class_name": "Edit", "title": "", "rect": {}},
                ],
            }, ensure_ascii=False),
        )
        db.add(el)
        db.commit()
        await run_handler("pickElementAuto",
                          {"elementName": "记事本Edit-自动路径", "levelIndex": -1, "resultVar": "edit"}, rr)
        pres = _last_result(rr)
        assert pres.get("found"), f"pickElementAuto(win32) 未找到: {pres}"
        assert pres.get("via") == "win32", f"应走 win32 通道: {pres}"
        ref = rr.vars.get("edit")
        assert isinstance(ref, dict) and ref.get("desktop_ref") == "win32"
        assert ref.get("hwnd") == edit_hwnd, f"hwnd 不一致: {ref}"
    finally:
        await _close(r)
        db.query(models.WorkflowElement).filter_by(name="记事本Edit-自动路径").delete()
        db.commit()
        db.close()
