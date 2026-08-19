"""调研脚本：Chromium 网页元素是否支持 IUIAutomationObjectModelPattern，
以及能否通过 GetUnderlyingObjectModel 拿到底层 DOM 引用 / 更多 HTML 属性。

背景：UIA 可访问性树只暴露 id/class/role/aria-* 等语义，拿不到 placeholder/
value/data-*/name 等普通 DOM 属性。用户提议：支持 ObjectModel Pattern 的控件
可通过 IUIAutomationObjectModelPattern::GetUnderlyingObjectModel 拿到底层对象，
可能有更多信息。本脚本实证这一通道在 Edge/Chromium 上是否有效。

用法：
    python scripts/capture_gui/probe_object_model.py [x y]
    - 带坐标：直接对 (x,y) 处控件实验
    - 不带坐标：提示你把鼠标移到目标控件后按 Enter，读当前光标位置实验

对光标处控件依次：
    1. ControlFromPoint 拿 UIA 控件
    2. 读 IsObjectModelPatternAvailableProperty (30112)
    3. 若可用：GetPattern(10022) → GetUnderlyingObjectModel() 拿 IUnknown
    4. 打印指针 + 尝试 QueryInterface 候选接口，看能否读属性
"""
import ctypes
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, _ROOT)

import ctypes.wintypes as wt  # noqa: E402
import comtypes  # noqa: E402
from comtypes import GUID  # noqa: E402

from capture_gui import overlay as ov  # noqa: E402

# IAccessible2 / IAccessible 等候选接口（视 ObjectModel 返回而定）
IID_IAccessible2 = GUID("{89D1F902-3E16-499B-B406-3B48C97BCA8C}")
IID_IAccessible = GUID("{618736E0-3C3D-11CF-810C-00AA00389B71}")
IID_IUIAutomationElement = GUID("{D22108AA-8AC5-49A5-837B-37BBB3D7591E}")
IID_IRawElementProviderSimple = GUID("{D6DD68D1-86FD-4332-8666-9ABEDEA2D24C}")


def _get_cursor():
    pt = wt.POINT()
    ov._GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _query_iunknown(ptr, iid: GUID):
    """对 GetUnderlyingObjectModel 返回的 IUnknown 尝试 QueryInterface 到 iid。返回接口或 None。"""
    try:
        if not ptr:
            return None
        # ctypes.POINTER(comtypes.IUnknown) → 转 comtypes 对象
        comobj = comtypes.Interface(ptr)
        return comobj.QueryInterface(iid)
    except Exception as e:
        return ("QI FAIL", str(e))


def probe_at(x, y):
    print("=" * 64)
    print(f"光标 ({x},{y})")
    ov._com_init()
    try:
        import uiautomation as uia
        with uia.UIAutomationInitializerInThread():
            ctrl = uia.ControlFromPoint(x, y)
            if not ctrl:
                print("ControlFromPoint -> None")
                return
            print("control:", ctrl.ControlTypeName, "| class:", ctrl.ClassName,
                  "| aid:", ctrl.AutomationId, "| name:", (ctrl.Name or "")[:40])
            # 1) ObjectModelPattern 可用性
            try:
                avail = ctrl.GetPropertyValue(uia.PropertyId.IsObjectModelPatternAvailableProperty)
                print("IsObjectModelPatternAvailable =", avail)
            except Exception as e:
                print("avail err:", e); avail = False
            if not avail:
                print("→ Chromium 不支持 ObjectModelPattern（不可用）")
                # 退而求其次：LegacyIAccessible 有多少属性
                try:
                    lip = ctrl.GetLegacyIAccessiblePattern()
                    if lip:
                        print("  LegacyIAccessible 有，可另查 ia2")
                except Exception:
                    pass
                return
            # 2) 拿 ObjectModelPattern
            try:
                om = ctrl.GetPattern(uia.PatternId.ObjectModelPattern)
                print("GetPattern(ObjectModelPattern) ->", om)
            except Exception as e:
                print("getpattern err:", e); return
            if not om:
                print("→ GetPattern 返回空（可用但不支持实例）")
                return
            # 3) GetUnderlyingObjectModel
            try:
                ptr = om.GetUnderlyingObjectModel()
                print("GetUnderlyingObjectModel ->", ptr)
            except Exception as e:
                print("getunderlying err:", e); return
            # 4) 尝试 query 候选接口
            for label, iid in (("IAccessible2", IID_IAccessible2),
                               ("IAccessible(legacy)", IID_IAccessible),
                               ("IRawElementProviderSimple", IID_IRawElementProviderSimple)):
                r = _query_iunknown(ptr, iid)
                if isinstance(r, tuple):
                    print(f"  QI {label}: {r}")
                elif r is None:
                    print(f"  QI {label}: unsupported (None)")
                else:
                    print(f"  QI {label}: OK -> {r}")
    finally:
        ov._com_uninit()


def main():
    if len(sys.argv) >= 3:
        x, y = int(sys.argv[1]), int(sys.argv[2])
        probe_at(x, y)
        return
    print("请把鼠标移到 Edge 的网页输入框/按钮上，然后按 Enter（Ctrl+C 退出）")
    while True:
        try:
            input(">>> 按 Enter 探测当前光标处控件（q 退出）... ")
        except (KeyboardInterrupt, EOFError):
            break
        x, y = _get_cursor()
        probe_at(x, y)


if __name__ == "__main__":
    main()