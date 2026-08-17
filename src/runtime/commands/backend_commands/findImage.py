"""Command: 图像查找 — findImage (backend)

用参考图在当前屏幕（纯 Python 截屏，浏览器/桌面统一）或浏览器页面内容中做模板匹配。
scope=screen：截虚拟屏幕（所有显示器），匹配坐标即屏幕坐标；
scope=page：扩展截浏览器页面内容（可后台截），坐标经视口换算。
"""
import os

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import convert_value
from src.repo.models import SessionLocal
from src.service.elements_service import resolve_image_ref

from ._vision import capture_page, capture_screen, template_match, screen_coords


def _settle(runner, step_id, instr, ok: bool, result):
    if ok:
        runner.completed += 1
        runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                               "status": "success", "result": result})
        return {"status": "success", "result": result}
    runner.results.append({"stepId": step_id, "nodeId": instr.get("nodeId"),
                           "status": "error", "result": result})
    return {"status": "error", "result": result}


@register_handler(
    cmd="findImage", label="图像查找",
    category="图像识别", runtime="backend",
    icon="fa-image", icon_color="text-pink-500", bg_color="bg-pink-50",
    description="用参考图在当前屏幕（默认，纯 Python 截全屏，浏览器/桌面统一）或浏览器页面内容中做模板匹配，返回匹配位置与屏幕坐标",
    category_order=55, command_order=10,
    summary_tpl="{imageRef}",
)
class FindImageHandler:
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

        if not image_ref or not os.path.isfile(image_ref):
            result = {"error": f"参考图不存在或元素未注册: {image_ref_raw}"}
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return _settle(runner, step_id, instr, False, result)

        from PIL import Image
        try:
            needle = Image.open(image_ref).convert("RGB")
            if scope == "screen":
                # 纯 Python 截屏：匹配坐标 = 屏幕坐标（offset 已含负坐标副屏）
                hay, off_x, off_y = capture_screen()
            elif scope == "page":
                # 浏览器页面内容：扩展 captureVisibleTab（可后台截），坐标需视口换算
                hay, sx, sy, dpr = await capture_page(runner, timeout)
            else:
                result = {"error": f"未知 scope: {scope}"}
                await runner._emit({"type": "stepError", "stepId": step_id,
                                    "nodeId": instr.get("nodeId"), "error": result["error"]})
                return _settle(runner, step_id, instr, False, result)

            m = template_match(hay, needle, similarity)
        except Exception as e:
            result = {"error": f"图像查找失败: {e}"}
            await runner._emit({"type": "stepError", "stepId": step_id,
                                "nodeId": instr.get("nodeId"), "error": result["error"]})
            return _settle(runner, step_id, instr, False, result)

        if m is None:
            result = {"found": False, "log": "未找到匹配图像"}
            return _settle(runner, step_id, instr, True, result)

        x, y, w, h, conf = m
        if scope == "page":
            screen_x, screen_y = screen_coords(sx, sy, dpr, x, y)
        else:  # screen：匹配坐标 + 虚拟屏幕偏移 = 屏幕物理坐标
            screen_x, screen_y = off_x + x, off_y + y
        result = {
            "found": True,
            "x": x, "y": y, "w": w, "h": h,
            "confidence": round(conf, 4),
            "screenX": screen_x, "screenY": screen_y,
            "imageWidth": hay.width, "imageHeight": hay.height,
            "log": f"找到图像 @({x},{y}) conf={conf:.3f} 屏幕=({screen_x},{screen_y})",
        }
        await runner._emit({"type": "stepComplete", "stepId": step_id,
                            "nodeId": instr.get("nodeId"), "result": result})
        return _settle(runner, step_id, instr, True, result)
