"""RPA 后端 REST 客户端：httpx 薄封装 + JWT 认证（ADR-0011）。

认证优先级：RPA_API_TOKEN > RPA_USERNAME/RPA_PASSWORD 登录换 token。
登录获取的 token 遇到 401 会自动重登一次。
"""

import httpx

from . import config


class RpaApiError(Exception):
    """后端非 2xx 或认证配置缺失时抛出，message 已含状态码与 detail。"""


class RpaClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._token: str = ""

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # 运行工作流是长阻塞调用，读超时放宽到 10 分钟
            self._client = httpx.AsyncClient(
                base_url=config.backend_url(),
                timeout=httpx.Timeout(600.0, connect=10.0),
            )
        return self._client

    @staticmethod
    def _checked(resp: httpx.Response):
        if resp.status_code >= 400:
            detail: object = resp.text[:500]
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                pass
            raise RpaApiError(f"HTTP {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    async def _ensure_token(self) -> str:
        if self._token:
            return self._token
        token = config.api_token()
        if token:
            self._token = token
            return token
        user, pwd = config.username(), config.password()
        if not user or not pwd:
            raise RpaApiError(
                "未配置认证：请设置 RPA_API_TOKEN 或 RPA_USERNAME/RPA_PASSWORD"
            )
        client = await self._ensure_client()
        resp = await client.post(
            "/api/auth/login", json={"username": user, "password": pwd}
        )
        data = self._checked(resp)
        self._token = data.get("access_token", "")
        if not self._token:
            raise RpaApiError("登录成功但响应缺少 access_token")
        return self._token

    async def request(self, method: str, path: str, *, auth: bool = True, **kwargs):
        client = await self._ensure_client()
        headers: dict = kwargs.pop("headers", None) or {}
        if auth:
            headers["Authorization"] = f"Bearer {await self._ensure_token()}"
        resp = await client.request(method, path, headers=headers, **kwargs)
        if resp.status_code == 401 and auth and not config.api_token():
            self._token = ""
            headers["Authorization"] = f"Bearer {await self._ensure_token()}"
            resp = await client.request(method, path, headers=headers, **kwargs)
        return self._checked(resp)

    async def get(self, path: str, **kwargs):
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs):
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs):
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs):
        return await self.request("DELETE", path, **kwargs)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


_client = RpaClient()


def get_client() -> RpaClient:
    return _client
