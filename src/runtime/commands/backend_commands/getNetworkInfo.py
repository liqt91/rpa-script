"""读取本机网络连接信息 — getNetworkInfo (backend)

优先使用 psutil 采集网卡/接口、活动 TCP/UDP 连接、主机 IP；未安装 psutil 时降级用
stdlib（socket 取地址列表/接口名，netstat 取连接）。结果可写入变量供下游引用。
"""
import re
import socket

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import clean_var_ref

_SCOPES = ("all", "interface", "connection", "host")

# MAC 地址（如 "C4-EF-BB-74-4F-C8" / "aa:bb:cc:dd:ee:ff"）识别，跨平台兼容 family 缺失
_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}$")

# 地址族 → 语义标签（psutil snicaddr/net_connection 的 family）
_FAMILY_LABELS = {
    socket.AF_INET: "ipv4",
    socket.AF_INET6: "ipv6",
    getattr(socket, "AF_LINK", -1): "mac",
}


def _family_label(family) -> str:
    return _FAMILY_LABELS.get(family, str(family))


def _addr_to_str(addr) -> str:
    """将 psutil laddr/raddr（ip+port 命名元组）格式化成 ip:port；空地址返回空串。"""
    if addr is None:
        return ""
    ip = getattr(addr, "ip", None)
    port = getattr(addr, "port", None)
    if ip is None:
        # 非命名元组（如空元组 () / 原始元组）时尝试按下标取
        if isinstance(addr, (tuple, list)) and addr:
            ip = addr[0]
            if len(addr) > 1:
                port = addr[1]
        else:
            ip = addr
    if ip is None:
        return ""
    ip = str(ip)
    if not ip or ip == "()":
        return ""
    try:
        port = int(port)
    except (TypeError, ValueError, OverflowError):
        port = None
    if port is None:
        return ip
    if ":" in ip:  # ipv6 用方括号包围
        return f"[{ip}]:{port}"
    return f"{ip}:{port}"


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ── 接口/网卡 ─────────────────────────────────────────────────────────────
def _collect_interfaces() -> dict:
    """采集网卡/接口信息。psutil 优先，失败则退回 socket.if_nameindex。"""
    try:
        import psutil
    except Exception:  # noqa: BLE001
        psutil = None

    try:
        idx_map = {name: idx for idx, name in socket.if_nameindex()}
    except (OSError, AttributeError):
        idx_map = {}

    detail = []
    addrs = {}
    stats = {}
    counters = {}
    names = set()
    if psutil is not None:
        try:
            addrs = psutil.net_if_addrs() or {}
        except Exception:  # noqa: BLE001
            addrs = {}
        try:
            stats = psutil.net_if_stats() or {}
        except Exception:  # noqa: BLE001
            stats = {}
        try:
            counters = psutil.net_io_counters(pernic=True) or {}
        except Exception:  # noqa: BLE001
            counters = {}
    if not addrs:
        # 退化：只有接口名与索引
        names = set(idx_map.keys())
    else:
        names = set(addrs.keys())

    for name in names:
        addr_list = []
        for a in addrs.get(name, []) or []:
            fam = _family_label(a.family) if getattr(a, "family", None) is not None else _family_label(socket.AF_INET)
            raw_addr = getattr(a, "address", None) or ""
            if _MAC_RE.match(str(raw_addr).strip()):
                fam = "mac"
            entry = {"family": fam, "address": raw_addr}
            if getattr(a, "netmask", None):
                entry["netmask"] = a.netmask
            if fam == "ipv4" and getattr(a, "broadcast", None):
                entry["broadcast"] = a.broadcast
            addr_list.append(entry)
        st = stats.get(name)
        cnt = counters.get(name)
        item = {
            "name": name,
            "index": idx_map.get(name),
            "isUp": bool(st.isup) if st is not None else None,
            "speed": st.speed if st is not None else None,
            "mtu": st.mtu if st is not None else None,
            "addresses": addr_list,
        }
        if cnt is not None:
            item.update({
                "sentBytes": cnt.bytes_sent,
                "recvBytes": cnt.bytes_recv,
                "sentPackets": cnt.packets_sent,
                "recvPackets": cnt.packets_recv,
                "rxErrors": cnt.errin,
                "txErrors": cnt.errout,
            })
        detail.append(item)

    detail.sort(key=lambda x: (x.get("index") is None, x.get("index") or 0, x["name"].lower()))
    return {"count": len(detail), "list": detail}


# ── 活动连接 ─────────────────────────────────────────────────────────────
def _netstat_snapshot() -> list:
    """Windows `netstat -ano` 解析（psutil 不可用时的降级方案）。"""
    import subprocess

    try:
        proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=20)
    except Exception:  # noqa: BLE001
        return []
    out = proc.stdout or ""
    detail = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4 or parts[0] not in ("TCP", "UDP"):
            continue
        proto = parts[0]
        local = parts[1] if len(parts) > 1 else ""
        remote = parts[2] if len(parts) > 2 else ""
        state = ""
        if proto == "TCP":
            state = parts[3] if len(parts) > 3 else ""
            pid = parts[-1]
        else:
            state = ""
            pid = parts[3] if len(parts) > 3 else ""
        # 从首个字段反推协议族：UDP 无 State，IPv6 地址带方括号
        family = "ipv6" if ("[" in local or local.count(":") > 1) else "ipv4"
        detail.append({
            "family": family,
            "type": "tcp" if proto == "TCP" else "udp",
            "local": local,
            "remote": remote,
            "state": state,
            "pid": _int_or_none(pid),
            "process": None,
            "fd": None,
        })
    return detail


def _collect_connections() -> dict:
    """采集活动 TCP/UDP 连接。psutil 优先，失败则退回 netstat 解析。"""
    try:
        import psutil
    except Exception:  # noqa: BLE001
        psutil = None

    proc_cache: dict = {}

    def _proc_name(pid):
        if pid is None or pid <= 0:
            return None
        if pid in proc_cache:
            return proc_cache[pid]
        name = None
        try:
            name = psutil.Process(pid).name()
        except Exception:  # noqa: BLE001
            name = None
        proc_cache[pid] = name
        return name

    detail = []
    if psutil is not None:
        try:
            conns = psutil.net_connections(kind="inet")
        except Exception:  # noqa: BLE001 (许可不足/平台不支持时不中断)
            conns = []
        for c in conns:
            ltype = "tcp"
            if c.type == socket.SOCK_DGRAM:
                ltype = "udp"
            elif c.type != socket.SOCK_STREAM:
                ltype = str(c.type)
            detail.append({
                "family": _family_label(c.family),
                "type": ltype,
                "local": _addr_to_str(c.laddr),
                "remote": _addr_to_str(c.raddr),
                "state": getattr(c, "status", "") or "",
                "pid": c.pid,
                "process": _proc_name(c.pid),
                "fd": c.fd,
            })
    else:
        detail = _netstat_snapshot()

    # 结果可读性排序：先 TCP，再按 pid 排序
    detail.sort(key=lambda x: (0 if x["type"] == "tcp" else 1, x["pid"] or 0, x["local"]))
    tcp = sum(1 for x in detail if x["type"] == "tcp")
    udp = sum(1 for x in detail if x["type"] == "udp")
    listen = sum(1 for x in detail if x["state"] == "LISTEN")
    return {"count": len(detail), "tcp": tcp, "udp": udp, "listen": listen, "list": detail}


# ── 主机信息 ─────────────────────────────────────────────────────────────
def _collect_host() -> dict:
    """采集主机名与本地 IP 列表（stdlib socket，不依赖 psutil）。"""
    try:
        hostname = socket.gethostname() or ""
    except OSError:
        hostname = ""
    ipv4: list = []
    ipv6: list = []
    seen: set = set()
    try:
        addrinfo = socket.getaddrinfo(socket.gethostname() or "localhost", None)
    except socket.gaierror:
        addrinfo = []
    for fam, _, _, _, sockaddr in addrinfo:
        ip = str(sockaddr[0])
        base = ip.split("%")[0]  # 去掉 ipv6 作用域 id
        if base in seen:
            continue
        seen.add(base)
        if ":" in base:
            if base not in ipv6:
                ipv6.append(base)
        else:
            if base not in ipv4:
                ipv4.append(base)
    return {
        "hostname": hostname,
        "ipv4": ipv4,
        "ipv6": ipv6,
        "ipv4Count": len(ipv4),
        "ipv6Count": len(ipv6),
    }


# ── 汇总 ─────────────────────────────────────────────────────────────────
def _summarize(info: dict, scope: str) -> str:
    parts = []
    if scope in ("all", "interface") and "interface" in info:
        i = info["interface"]
        parts.append(f"网卡/接口 {i.get('count', 0)} 个")
    if scope in ("all", "connection") and "connection" in info:
        c = info["connection"]
        parts.append(
            f"网络连接 {c.get('count', 0)} 条"
            f"（TCP {c.get('tcp', 0)}、UDP {c.get('udp', 0)}、监听 {c.get('listen', 0)}）"
        )
    if scope in ("all", "host") and "host" in info:
        h = info["host"]
        parts.append(f"主机 {h.get('hostname', '') or '未知'}，IPv4 {h.get('ipv4Count', 0)} 个")
    return "；".join(parts) or "未读取到网络信息"


def _build_info(scope: str) -> dict:
    info: dict = {}
    if scope in ("all", "interface"):
        info["interface"] = _collect_interfaces()
    if scope in ("all", "connection"):
        info["connection"] = _collect_connections()
    if scope in ("all", "host"):
        info["host"] = _collect_host()
    return info


@register_handler(cmd="getNetworkInfo", label="获取本机网络连接信息",
    category="桌面操作", runtime="backend",
    icon="fa-network-wired", icon_color="text-indigo-500",
    bg_color="bg-indigo-50",
    description="读取本机网络连接信息（网卡/接口、活动 TCP/UDP 连接、主机 IP）。优先用 psutil，未安装时降级用 socket/netstat。结果可写入变量供下游引用。",
    category_order=50,
    command_order=26,
)
class GetNetworkInfoHandler:
    params = [
        Param("scope", "读取范围", "select", default="all", options=[{"label": "全部网络信息", "value": "all"}, {"label": "网卡/接口", "value": "interface"}, {"label": "网络连接", "value": "connection"}, {"label": "主机信息", "value": "host"}]),
        Param("resultVar", "结果存入变量", "str-var", default="", group="output", placeholder="读取到的网络信息字典存入此变量，如 networkInfo"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})

        scope = extra.get("scope", "all")
        if not isinstance(scope, str) or scope not in _SCOPES:
            scope = "all"
        result_var = clean_var_ref(extra.get("resultVar", ""))

        try:
            info = _build_info(scope)
        except Exception as e:  # noqa: BLE001 — 读取失败不应中断流程
            info = {"error": f"{e}"}

        if result_var:
            runner.vars[result_var] = info

        result = {**info, "scope": scope, "log": _summarize(info, scope)}
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
