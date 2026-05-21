"""
脚本调用服务端 AI 接口的桥接模块（透传模式）。

鉴权信息获取优先级：
    1. 环境变量 SCRAPER_SERVER_URL / SCRAPER_TOKEN（client.py run/pull/submit 时注入）
    2. client_config.json（setup 时持久化的 token + server url，支持 IDE 直接运行）

用法（在 jobs/<name>/main.py 的 run() 中）：
    from shared.ai_bridge import invoke

    # 直接透传 Dify 请求体，服务端只做校验 + 加 appkey
    result = invoke("sentiment", {
        "query": "分析以下评论的情感倾向...",
        "inputs": {},
        "response_mode": "blocking",
        "user": "scraper-client"
    })

返回：Dify 原始响应（结构取决于 app_type）
"""

import json
import os
from pathlib import Path
from typing import Optional

import httpx


_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "client_config.json"


def _read_client_config() -> tuple[Optional[str], Optional[str]]:
    """从 client_config.json 读取 server_url 和 token。"""
    if not _CONFIG_PATH.exists():
        return None, None
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        url = cfg.get("server", {}).get("url", "")
        token = cfg.get("token", "")
        return url.rstrip("/") if url else None, token if token else None
    except Exception:
        return None, None


def _get_env() -> tuple[str, str]:
    """获取服务端地址和 token。优先环境变量，fallback client_config.json。"""
    base = os.environ.get("SCRAPER_SERVER_URL", "").rstrip("/")
    token = os.environ.get("SCRAPER_TOKEN", "")

    if not base or not token:
        cfg_url, cfg_token = _read_client_config()
        base = base or (cfg_url or "")
        token = token or (cfg_token or "")

    if not base:
        raise RuntimeError(
            "ai_bridge: 缺少服务端地址。"
            "请运行 `python client.py setup` 配置，或设置 SCRAPER_SERVER_URL 环境变量。"
        )
    if not token:
        raise RuntimeError(
            "ai_bridge: 缺少鉴权 token。"
            "请运行 `python client.py login` 刷新 token，或设置 SCRAPER_TOKEN 环境变量。"
        )
    return base, token


def invoke(capability: str, payload: dict) -> dict:
    """
    调用服务端 /api/ai/invoke 透传接口。

    Args:
        capability: AI 能力标识，如 sentiment / summary / topics
        payload: Dify 原始请求体。格式取决于目标 app_type：
            - text:       {"query": "...", "inputs": {}, "response_mode": "blocking", "user": "..."}
            - chat/agent/chatflow: 同上，可额外传 "conversation_id"
            - workflow:   {"inputs": {...}, "response_mode": "blocking", "user": "..."} (无 query)

    Returns:
        Dify 原始响应（结构取决于 app_type）
    """
    base, token = _get_env()
    url = f"{base}/api/ai/invoke"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "capability": capability,
        "payload": payload,
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()


def is_available() -> bool:
    """判断当前环境是否配置了 AI 桥接（环境变量或 client_config.json）。"""
    env_ok = bool(os.environ.get("SCRAPER_SERVER_URL")) and bool(os.environ.get("SCRAPER_TOKEN"))
    if env_ok:
        return True
    url, token = _read_client_config()
    return bool(url) and bool(token)
