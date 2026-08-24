"""
DeepSeek 调用 — deepseekChat (backend)
"""
import os

import httpx

from src.runtime.workflow.handlers.registry import register_handler, Param
from src.runtime.workflow.handlers.utils import resolve_vars, clean_var_ref

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1/chat/completions"


@register_handler(cmd="deepseekChat", label="DeepSeek 调用",
    category="AI 调用", runtime="backend",
    icon="fa-robot", icon_color="text-violet-500",
    bg_color="bg-violet-50",
    description="调用 DeepSeek Chat Completions API，返回回复正文并写入变量",
    category_order=40,
    command_order=10,
)
class DeepseekChatHandler:
    params = [
        Param("prompt", "提示词（用户消息）", "text", required=True, placeholder="要发给 DeepSeek 的内容，支持 {{变量}}"),
        Param("systemPrompt", "系统提示词（System）", "text", group="advanced", placeholder="可选，设定 AI 的角色 / 规则 / 输出格式"),
        Param("model", "模型", "select", default="deepseek-chat", options=[{"label": "deepseek-chat", "value": "deepseek-chat"}, {"label": "deepseek-reasoner", "value": "deepseek-reasoner"}, {"label": "deepseek-v4-pro", "value": "deepseek-v4-pro"}]),
        Param("temperature", "温度", "number", default=0.3, group="advanced"),
        Param("maxTokens", "最大回复长度", "number", default=2048, group="advanced"),
        Param("apiKey", "API Key", "string", group="advanced", placeholder="留空则使用环境变量 AI_API_KEY"),
        Param("baseUrl", "API 地址", "string", group="advanced", placeholder="留空使用 https://api.deepseek.com/v1/chat/completions"),
        Param("outputVar", "结果变量名", "str-var", default="deepseekResult", group="output", description="回复正文将存入该变量"),
    ]

    @staticmethod
    async def execute(runner, cmd_type, step_id, instr):
        extra = instr.get("extra", {})

        prompt = resolve_vars(str(extra.get("prompt") or ""), runner.vars)
        if not prompt.strip():
            raise ValueError("deepseekChat: 提示词（prompt）不能为空")

        system_prompt = resolve_vars(str(extra.get("systemPrompt") or ""), runner.vars)
        model = str(extra.get("model") or "deepseek-chat")

        try:
            temperature = float(extra.get("temperature", 0.3))
        except (TypeError, ValueError):
            temperature = 0.3
        try:
            max_tokens = int(extra.get("maxTokens", 2048))
        except (TypeError, ValueError):
            max_tokens = 2048

        api_key = str(extra.get("apiKey") or os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or "")
        if not api_key:
            raise ValueError("deepseekChat: 未配置 API Key（请填写 apiKey 或在 .env 设置 AI_API_KEY）")

        base_url = str(extra.get("baseUrl") or _DEFAULT_BASE_URL)

        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(base_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}

        # 写入结果变量（默认 deepseekResult）
        output_var = clean_var_ref(str(extra.get("outputVar") or "deepseekResult"))
        if output_var:
            runner.vars[output_var] = content

        result = {
            "cmd": "deepseekChat",
            "content": content,
            "model": data.get("model") or model,
            "finishReason": choice.get("finish_reason"),
            "usage": usage,
        }

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

    # 底稿指向: src/runtime/commands/backend_commands/deepseekChat.py
