"""MCP 服务器配置（ADR-0011）：全部来自环境变量，不依赖其他层。"""

import os


def backend_url() -> str:
    """后端地址：RPA_BACKEND_URL 优先；否则读端口文件（随机端口 8100-8199）自适应；兜底 8000。"""
    env_url = os.environ.get("RPA_BACKEND_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")
    # 端口文件：RPA_DATA_DIR/backend.port，其次仓库 data/backend.port
    candidates = []
    if os.environ.get("RPA_DATA_DIR"):
        candidates.append(os.path.join(os.environ["RPA_DATA_DIR"], "backend.port"))
    repo_data = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    candidates.append(os.path.join(repo_data, "backend.port"))
    for cand in candidates:
        try:
            with open(cand, "r", encoding="utf-8") as f:
                port = f.read().strip()
            if port.isdigit():
                return f"http://127.0.0.1:{port}"
        except OSError:
            continue
    return "http://127.0.0.1:8000"


def api_token() -> str:
    return os.environ.get("RPA_API_TOKEN", "")


def username() -> str:
    return os.environ.get("RPA_USERNAME", "")


def password() -> str:
    return os.environ.get("RPA_PASSWORD", "")


def enabled_tool_groups() -> set[str]:
    """RPA_MCP_TOOLS=read,write,run,browser 白名单；空则全部启用。"""
    raw = os.environ.get("RPA_MCP_TOOLS", "").strip()
    if not raw:
        return {"read", "write", "run", "browser"}
    return {g.strip() for g in raw.split(",") if g.strip()}


def http_host() -> str:
    return os.environ.get("RPA_MCP_HTTP_HOST", "127.0.0.1")


def http_port() -> int:
    return int(os.environ.get("RPA_MCP_HTTP_PORT", "8765"))
