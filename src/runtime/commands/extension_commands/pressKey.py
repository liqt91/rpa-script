"""Command: 按键"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="pressKey", label="按键",
    category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="向页面发送键盘按键。OS级keybd_event发送，页面按键和浏览器快捷键均可生效",
    category_order=60,
    command_order=30,
    summary_tpl="{key}",
)
class PressKeyHandler:
    params = [
        Param("key", "按键", "select", required=True, default="Enter", options=[{"label": "Enter 回车", "value": "Enter"}, {"label": "Tab 制表", "value": "Tab"}, {"label": "Escape 取消", "value": "Escape"}, {"label": "Backspace 退格", "value": "Backspace"}, {"label": "Delete 删除", "value": "Delete"}, {"label": "Space 空格", "value": " "}, {"label": "ArrowUp ↑", "value": "ArrowUp"}, {"label": "ArrowDown ↓", "value": "ArrowDown"}, {"label": "ArrowLeft ←", "value": "ArrowLeft"}, {"label": "ArrowRight →", "value": "ArrowRight"}, {"label": "PageUp 上翻", "value": "PageUp"}, {"label": "PageDown 下翻", "value": "PageDown"}, {"label": "Home", "value": "Home"}, {"label": "End", "value": "End"}, {"label": "F1 帮助 [需OS]", "value": "F1"}, {"label": "F5 刷新 [需OS]", "value": "F5"}, {"label": "F12 开发者工具 [需OS]", "value": "F12"}, {"label": "Ctrl+C 复制 [需OS+modifier=Ctrl]", "value": "c"}, {"label": "Ctrl+V 粘贴 [需OS+modifier=Ctrl]", "value": "v"}, {"label": "Ctrl+A 全选 [需OS+modifier=Ctrl]", "value": "a"}, {"label": "Ctrl+Z 撤销 [需OS+modifier=Ctrl]", "value": "z"}], description="F1-F12等浏览器快捷键必须选[模拟人工操作]走OS通道才能生效"),
        Param("modifiers", "修饰键", "string", default="", group="advanced", placeholder="Ctrl,Alt,Shift, 可多个逗号分隔", description="同时按下的修饰键。Ctrl+C/V/A/Z 需要 modifier=Ctrl。注意：Ctrl+T/W/N 等浏览器标签页快捷键也会生效"),
    ]