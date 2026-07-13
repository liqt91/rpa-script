"""Command: 按键"""
from src.runtime.workflow.handlers.registry import register_handler, Param

@register_handler(cmd="pressKey", label="按键",
    category="页面操作", runtime="extension",
    icon="fa-keyboard", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="向页面发送键盘按键",
    category_order=60,
    command_order=30,
)
class PressKeyHandler:
    params = [
        Param("key", "按键", "select", required=True, default="Enter", options=[{"label": "Enter 回车", "value": "Enter"}, {"label": "Tab 制表", "value": "Tab"}, {"label": "Escape 取消", "value": "Escape"}, {"label": "Backspace 退格", "value": "Backspace"}, {"label": "Delete 删除", "value": "Delete"}, {"label": "Space 空格", "value": " "}, {"label": "ArrowUp ↑", "value": "ArrowUp"}, {"label": "ArrowDown ↓", "value": "ArrowDown"}, {"label": "ArrowLeft ←", "value": "ArrowLeft"}, {"label": "ArrowRight →", "value": "ArrowRight"}, {"label": "PageUp 上翻", "value": "PageUp"}, {"label": "PageDown 下翻", "value": "PageDown"}, {"label": "Home", "value": "Home"}, {"label": "End", "value": "End"}, {"label": "F1", "value": "F1"}, {"label": "F5 刷新", "value": "F5"}, {"label": "F12", "value": "F12"}, {"label": "Ctrl+C 复制", "value": "c"}, {"label": "Ctrl+V 粘贴", "value": "v"}, {"label": "Ctrl+A 全选", "value": "a"}, {"label": "Ctrl+Z 撤销", "value": "z"}], description="键盘按键名称，支持键盘事件标准 key 值。常用：Enter、Tab、Escape、Backspace、ArrowUp/Down/Left/Right、Space"),
        Param("modifiers", "修饰键", "string", default="", group="advanced", placeholder="Ctrl,Alt,Shift, 可多个逗号分隔", description="同时按下的修饰键，多个用逗号分隔。如 Ctrl,Shift+字母键可输入大写。注意：部分组合键(如 Ctrl+C)系统拦截，页面收不到"),
    ]