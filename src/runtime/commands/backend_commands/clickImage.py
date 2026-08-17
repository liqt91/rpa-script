"""Command: 图像点击 — clickImage (backend)

用参考图在当前屏幕（默认，纯 Python 截屏，浏览器/桌面统一）做模板匹配，
找到后真实点击匹配位置（OS 级鼠标，需窗口前台）。未找到按 onError 处理。
复用 P0 的用户鼠标空闲检测 / 屏幕越界检查。
"""
import os

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value
from src.repo.models import SessionLocal
from src.service.elements_service import resolve_image_ref

from ._vision import capture_page, capture_screen, template_match, screen_coords


@register_handler(
    cmd="clickImage", label="图像点击",
    category="图像识别", runtime="backend",
    icon="fa-hand-pointer", icon_color="text-pink-500", bg_color="bg-pink-50",
    description="用参考图在当前屏幕（默认，纯 Python 截屏，浏览器/桌面统一）做模板匹配，找到后真实点击匹配位置（OS 级鼠标，需窗口前台）。未找到按 onError 处理",
    category_order=55, command_order=20,
    summary_tpl="{imageRef}",
)
class ClickImageHandler:
    params = [
        Param("imageRef", "参考图元素", "element", required=True,
              placeholder="从元素库选择图像元素（上传的参考图）"),
        Param("scope", "匹配范围", "select", default="screen",
              options=[{"label": "全屏幕（默认，所见即所得）", "value": "screen"},
                       {"label": "浏览器页面内容（需扩展，后台可截）", "value": "page"}], group="advanced"),
        Param("similarity", "相似度阈值", "number", default=0.8, group="advanced"),
        Param("timeout", "超时(秒)", "number", default=10, group="advanced"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from src.runtime.workflow.extension_runner import (
            _os_move_mouse, _os_click, _user_mouse_idle, _in_screen,
        )

        extra = instr.get("extra", {})
        image_ref_raw = convert_value(extra.get("imageRef", ""), "string", runner.vars)
        scope = extra.get("scope", "screen")
        similarity_raw = extra.get("similarity")

        # 解析 imageRef：元素库 image 元素名 → 参考图路径 + 默认相似度；否则视为文件路径
        db = SessionLocal()
        try:
            ref = resolve_image_ref(db, image_ref_raw)
        finally:
            db.close()
        image_ref = ref.get("path", "") or ""
        similarity = float(similarity_raw) if similarity_raw is not None else (
            ref.get("similarity") if ref.get("similarity") is not None else 0.8
        )
        timeout = float(extra.get("timeout", 10) or 10)

        async def fail(msg):
            result = {"error": msg, "clicked": False}
            runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                                   "status": "error", "result": result})
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": msg})
            return False

        if not image_ref or not os.path.isfile(image_ref):
            return await fail(f"参考图不存在或元素未注册: {image_ref_raw}")

        from PIL import Image
        try:
            needle = Image.open(image_ref).convert("RGB")
            if scope == "screen":
                hay, off_x, off_y = capture_screen()
            elif scope == "page":
                hay, sx, sy, dpr = await capture_page(runner, timeout)
            else:
                raise RuntimeError(f"未知 scope: {scope}")
            m = template_match(hay, needle, similarity)
        except Exception as e:
            return await fail(f"图像识别失败: {e}")

        if m is None:
            return await fail(f"未找到图像（similarity={similarity}），未点击")

        x, y, w, h, conf = m
        if scope == "page":
            screen_x, screen_y = screen_coords(sx, sy, dpr, x, y)
        else:  # screen：匹配坐标 + 虚拟屏幕偏移 = 屏幕物理坐标
            screen_x, screen_y = off_x + x, off_y + y

        # 越界检查：目标不在任何显示器内 → 跳过点击
        if not _in_screen(screen_x, screen_y):
            return await fail(f"目标屏幕坐标 ({screen_x},{screen_y}) 不在任何显示器内，未点击")

        # 用户抢鼠标检测：空闲才移动真实光标
        if not _user_mouse_idle():
            return await fail("检测到用户正在使用鼠标，已跳过真实点击（请稍后重试）")

        _os_move_mouse(screen_x, screen_y)
        import time
        time.sleep(0.1)
        _os_click()

        result = {
            "clicked": True,
            "x": x, "y": y, "w": w, "h": h,
            "confidence": round(conf, 4),
            "screenX": screen_x, "screenY": screen_y,
            "log": f"已点击图像 @({x},{y}) conf={conf:.3f}",
        }
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return True
