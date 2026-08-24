"""读取系统字体列表 — readSystemFonts (backend)

Windows 读取字体注册表（HKLM/HKCU 的 ...\\NT\\CurrentVersion\\Fonts），
非 Windows 降级用 fc-list（Linux/macOS）或直接返回空列表。结果可写入变量供下游引用，
如生成文档/选择字体样式。
"""
import os
import re

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


# ── Windows 字体注册表 ────────────────────────────────────────────────────
# 值名形如 "Arial (TrueType)"、"Bahnschrift (OpenType)"，值数据为字体文件名（或完整路径）。
_FONT_REG_PATHS = [
    ("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
]

# 常见字体类型标记，用于清理出干净的家族名（如 "Arial (TrueType)" → "Arial"）
_FONT_TYPE_RE = re.compile(
    r"\s*\((?:TrueType|OpenType|Type 1|Type1|All Res|All res|PostScript|OTF|TTF|FON)\)\s*$",
    re.I,
)


def _clean_font_name(raw) -> str:
    """清理注册表值名为纯字体家族/显示名。"""
    if not raw:
        return ""
    name = str(raw).strip()
    return _FONT_TYPE_RE.sub("", name).strip()


def _read_windows_registry() -> dict:
    """读取 HKLM/HKCU 字体注册表，返回 {家族名: 字体文件名}。"""
    import winreg

    entries: dict = {}
    for hive_name, subkey in _FONT_REG_PATHS:
        hive = getattr(winreg, hive_name)
        try:
            key = winreg.OpenKey(hive, subkey)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if not name:
                    continue
                family = _clean_font_name(name)
                if family:
                    entries[family] = str(value) if value else ""
        finally:
            key.Close()
    return entries


def _list_fonts_fc() -> list | None:
    """Linux/macOS 用 fc-list 枚举字体家族；失败返回 None。"""
    try:
        import subprocess

        proc = subprocess.run(
            ["fc-list", "--format=%{family}\n"],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0:
            return None
        fams: set = set()
        for line in proc.stdout.splitlines():
            for f in line.split(","):
                f = f.strip()
                if f:
                    fams.add(f)
        return sorted(fams)
    except Exception:
        return None


def _collect_fonts() -> tuple[dict, str]:
    """采集字体，返回 (entries: dict[family->file], source_name)。"""
    if os.name == "nt":
        return _read_windows_registry(), "registry"
    fc = _list_fonts_fc()
    if fc is not None:
        return {f: "" for f in fc}, "fc-list"
    return {}, "none"


def list_system_fonts(include_file: bool = False) -> dict:
    """读取系统已安装字体列表。

    Args:
        include_file: 是否在 list 明细中一并返回字体文件名/路径。

    Returns:
        {
          "count": int,
          "families": ["Arial", "Arial Bold", ...],        # 去重/排序后的家族名
          "list": [{"name": ..., "file": ...}, ...],        # 明细；未请求 include_file 时不含 file
          "source": "registry|fc-list|none|error",
          "platform": "windows|nt|posix 之类",
          "error": str?,                                    # 仅出错时
        }
    """
    entries, source = _collect_fonts()
    families = sorted(entries.keys(), key=lambda s: s.lower())
    if include_file:
        detail = [{"name": f, "file": entries.get(f, "")} for f in families]
    else:
        detail = [{"name": f} for f in families]
    return {
        "count": len(families),
        "families": families,
        "list": detail,
        "source": source,
        "platform": "windows" if os.name == "nt" else os.name,
    }


def _summarize(info: dict) -> str:
    """根据采集结果生成人类可读的摘要日志。"""
    count = info.get("count", 0)
    src = info.get("source", "")
    platform = info.get("platform", "")
    base = f"共读取到 {count} 种字体（来源：{src}，平台：{platform}）"
    if info.get("error"):
        base += f"；错误：{info['error']}"
    return base


@register_handler(cmd="readSystemFonts", label="读取系统字体列表",
    category="桌面操作", runtime="backend",
    icon="fa-font", icon_color="text-purple-500",
    bg_color="bg-purple-50",
    description="读取系统已安装字体列表（Windows 读取字体注册表，非 Windows 降级用 fc-list/字体目录）。结果可写入变量供下游引用，如生成文档/选择字体样式。",
    category_order=50,
    command_order=25,
)
class ReadSystemFontsHandler:
    params = [
        Param("includeFile", "包含字体文件", "boolean", default=False, group="advanced", description="是否在结果中一并返回每个字体对应的字体文件名/路径"),
        Param("resultVar", "结果存入变量", "str-var", default="", group="output", placeholder="读取到的字体列表字典存入此变量，如 fontList"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})
        include_file = bool(extra.get("includeFile", False))
        result_var = clean_var_ref(extra.get("resultVar", ""))

        try:
            info = list_system_fonts(include_file=include_file)
        except Exception as e:  # noqa: BLE001 — 读取失败不应中断流程
            info = {
                "count": 0, "families": [], "list": [],
                "source": "error", "platform": "windows" if os.name == "nt" else os.name,
                "error": f"{e}",
            }

        if result_var:
            runner.vars[result_var] = info

        result = {**info, "log": _summarize(info)}
        runner.completed += 1
        runner.results.append({
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "status": "success",
            "result": result,
        })
        await runner._emit({
            "type": "stepComplete",
            "stepId": step_id,
            "nodeId": instr.get("nodeId"),
            "result": result,
        })
        return True
