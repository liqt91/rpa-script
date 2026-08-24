"""读取系统硬件信息 — readHardwareInfo (backend)

通过 _win32.get_hardware_info() 采集系统硬件信息（CPU/内存/显卡/磁盘/主板/操作系统/BIOS），
按 scope 过滤，结果可写入变量供下游引用。Windows 下用 PowerShell(WMI) 取详细硬件，
非 Windows 降级返回 Python 层面信息（os/platform/psutil/shutil）。
"""
from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref


_SCOPES = ("all", "system", "cpu", "memory", "gpu", "disk")


def _summarize(info: dict, scope: str) -> str:
    """根据采集结果生成人类可读的摘要日志。"""
    parts = []

    sys_part = info.get("system")
    if sys_part and scope in ("all", "system"):
        py = sys_part.get("python") or {}
        if py.get("name"):
            parts.append(f"系统 {py['name']} {py.get('release', '')}".strip())
        maker = sys_part.get("manufacturer") or ""
        model = sys_part.get("model") or ""
        if maker or model:
            parts.append(f"机器 {maker} {model}".strip())

    cpu = info.get("cpu")
    if cpu:
        name = ""
        if cpu.get("list") and cpu["list"][0].get("name"):
            name = cpu["list"][0]["name"]
        pc = cpu.get("physicalCores")
        lc = cpu.get("logicalCores")
        detail_parts = []
        if pc:
            detail_parts.append(f"{pc}物理核")
        if lc:
            detail_parts.append(f"{lc}逻辑核")
        detail = f" {'/'.join(detail_parts)}" if detail_parts else ""
        parts.append(f"CPU {name}{detail}".strip())

    mem = info.get("memory")
    if mem:
        total = mem.get("total")
        if total:
            parts.append(f"内存 {_fmt(total)}")
        else:
            parts.append("内存 未知")

    gpu = info.get("gpu")
    if gpu and gpu.get("list"):
        names = [g.get("name", "") for g in gpu["list"] if g.get("name")]
        if names:
            parts.append("显卡 " + ", ".join(names))

    disk = info.get("disk")
    if disk and "list" in disk:
        parts.append(f"磁盘 {disk.get('count', len(disk['list']))} 个分区")

    return "；".join(parts) or "未读取到硬件信息"


def _fmt(n) -> str:
    """本地字节格式化（避免依赖 _win32.fmt_bytes 的跨模块引入）。"""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


@register_handler(cmd="readHardwareInfo", label="读取系统硬件信息",
    category="桌面操作", runtime="backend",
    icon="fa-microchip", icon_color="text-teal-500",
    bg_color="bg-teal-50",
    description="读取系统硬件信息（CPU/内存/显卡/磁盘/主板/操作系统/BIOS），结果可写入变量供下游引用；非 Windows 平台降级返回 Python 层面信息",
    category_order=50,
    command_order=24,
)
class ReadHardwareInfoHandler:
    params = [
        Param("scope", "读取范围", "select", default="all", options=[
            {"label": "全部硬件信息", "value": "all"},
            {"label": "系统信息", "value": "system"},
            {"label": "CPU", "value": "cpu"},
            {"label": "内存", "value": "memory"},
            {"label": "显卡", "value": "gpu"},
            {"label": "磁盘", "value": "disk"},
        ]),
        Param("resultVar", "结果存入变量", "str-var", default="",
              group="output", placeholder="读取到的硬件信息字典存入此变量，如 hardwareInfo"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        from ._win32 import get_hardware_info

        extra = instr.get("extra", {})
        scope = extra.get("scope", "all")
        if not isinstance(scope, str) or scope not in _SCOPES:
            scope = "all"
        result_var = clean_var_ref(extra.get("resultVar", ""))

        info = get_hardware_info(scope)

        if result_var:
            runner.vars[result_var] = info

        result = {**info, "log": _summarize(info, scope)}
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
