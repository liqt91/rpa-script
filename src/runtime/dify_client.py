"""
Dify 多应用客户端（透传模式）。

服务端只做三件事：
  1. 参数校验（按 app_type 校验必填/禁止字段）
  2. 添加 Authorization header（注入 app_key）
  3. 转发到 Dify，返回原始响应

不转换请求体结构，不解析/封装返回结果。
"""

import json
from typing import Optional

import httpx

from src.config import runtime_config as config


# app_type → endpoint 映射
ENDPOINTS = {
    "text": "/v1/completion-messages",
    "chat": "/v1/chat-messages",
    "agent": "/v1/chat-messages",
    "chatflow": "/v1/chat-messages",
    "workflow": "/v1/workflows/run",
}

# 各类型必填字段
REQUIRED_FIELDS = {
    "text": {"user"},
    "chat": {"user"},
    "agent": {"user"},
    "chatflow": {"user"},
    "workflow": {"user"},
}

# 各类型禁止字段
FORBIDDEN_FIELDS = {
    "text": {"conversation_id"},
    "workflow": {"query", "conversation_id"},
}


def _default_endpoint(app_type: str) -> str:
    return ENDPOINTS.get(app_type, "/v1/chat-messages")


def _validate_payload(app_type: str, payload: dict) -> list[str]:
    """按 app_type 校验 Dify 请求体。返回错误列表（空表示通过）。"""
    errors = []

    # 必填字段
    for field in REQUIRED_FIELDS.get(app_type, set()):
        if field not in payload:
            errors.append(f"缺少必填字段: {field}")

    # 禁止字段
    for field in FORBIDDEN_FIELDS.get(app_type, set()):
        if field in payload:
            errors.append(f"{app_type} 类型不支持 {field} 字段")

    # text/chat/agent/chatflow 必须有 query 或 inputs（至少一个非空）
    if app_type in ("text", "chat", "agent", "chatflow"):
        if not payload.get("query") and not payload.get("inputs"):
            errors.append(f"{app_type} 类型需要 query 或 inputs 至少一个非空")

    # workflow 必须有 inputs
    if app_type == "workflow":
        if not payload.get("inputs"):
            errors.append("workflow 类型需要 inputs 字段")

    return errors


class DifyClient:
    def __init__(self):
        self.base_url = config.DIFY_BASE_URL.rstrip("/") if config.DIFY_BASE_URL else ""
        self.timeout = 120.0

    def is_configured(self) -> bool:
        return bool(config.DIFY_BASE_URL)

    def list_capabilities(self) -> list[dict]:
        """根据 DIFY_APPS 配置动态生成能力列表。"""
        caps = []
        for cap_type, app_cfg in config.DIFY_APPS.items():
            if app_cfg.get("api_key"):
                caps.append({
                    "type": cap_type,
                    "name": app_cfg.get("name", cap_type),
                    "app_type": app_cfg.get("app_type", "chat"),
                })
        return caps

    def invoke(self, app_cfg: dict, payload: dict) -> dict:
        """
        透传调用 Dify。

        Args:
            app_cfg: AI 应用配置，至少包含 api_key, app_type
            payload: Dify 原始请求体

        Returns:
            Dify 原始响应字典
        """
        app_type = app_cfg.get("app_type", "chat")
        api_key = app_cfg.get("api_key", "")
        endpoint = app_cfg.get("endpoint") or _default_endpoint(app_type)

        if not api_key:
            raise ValueError(f"AI 应用未配置 API Key")

        # 参数校验
        errors = _validate_payload(app_type, payload)
        if errors:
            raise ValueError("; ".join(errors))

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    def get_parameters(self, app_cfg: dict) -> dict:
        """
        调用 Dify /v1/parameters 获取应用参数配置。

        Args:
            app_cfg: AI 应用配置，至少包含 api_key, app_type

        Returns:
            Dify 原始响应字典，包含 user_input_form、file_upload、system_parameters 等
        """
        app_type = app_cfg.get("app_type", "chat")
        api_key = app_cfg.get("api_key", "")

        if not api_key:
            raise ValueError(f"AI 应用未配置 API Key")

        # workflow 类型没有 parameters 接口
        if app_type == "workflow":
            raise ValueError("workflow 类型不支持获取应用参数")

        url = f"{self.base_url}/v1/parameters"
        headers = {"Authorization": f"Bearer {api_key}"}

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()


# ---------- 全局单例 ----------

_dify_client: Optional[DifyClient] = None


def get_dify_client() -> DifyClient:
    global _dify_client
    if _dify_client is None:
        _dify_client = DifyClient()
    return _dify_client
