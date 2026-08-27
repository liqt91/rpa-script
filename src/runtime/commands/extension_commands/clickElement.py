"""Command: 点击元素"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="clickElement", label="点击元素",
    category="浏览器元素操作", runtime="extension",
    icon="fa-hand-pointer", icon_color="text-blue-500",
    bg_color="bg-blue-50",
    description="点击页面上的一个元素",
    category_order=20,
    command_order=20,
)
class ClickElementHandler:
    params = [
        Param("elementName", "元素", "element", required=True),
        Param("scope", "匹配范围", "select", default="local", options=[{"label": "当前外层元素内", "value": "local"}, {"label": "全页面", "value": "global"}], group="advanced"),
        Param("loopAnchor", "锚点元素", "string", default="", group="anchor"),
        Param("visibilityMode", "元素可见性", "select", default="visible", options=[{"label": "仅可见", "value": "visible"}, {"label": "所有", "value": "any"}], group="advanced"),
        Param("humanLike", "真实鼠标点击", "boolean", default=True, group="advanced", description="勾选：鼠标贝塞尔移动并真实点击（需浏览器窗口在前台）；不勾选：合成 click 事件（快，后台可用）"),
        Param("clickMethod", "点击方式", "select", default="auto", options=[{"label": "自动（真实鼠标）", "value": "auto"}, {"label": "合成事件（不碰鼠标，后台可用）", "value": "js"}, {"label": "仅真实鼠标（需窗口前台）", "value": "os"}], group="advanced", description="auto：真实鼠标移动+点击（兼容现状）；js：页面内合成完整鼠标事件序列（mousemove/mousedown/mouseup/click），不移动系统鼠标、后台可用，适合被遮挡元素/反爬页；os：强制真实鼠标"),
        Param("scrollDelayMs", "点击前等待(ms)", "number", default=400, group="advanced", description="滚动到元素后、点击前的拟人化等待均值（毫秒）。反爬需要更慢节奏时调大"),
        Param("postClickDelayMs", "点击后等待(ms)", "number", default=300, group="advanced", description="真实点击后的拟人化等待均值（毫秒），仅在真实鼠标点击时生效"),
    ]