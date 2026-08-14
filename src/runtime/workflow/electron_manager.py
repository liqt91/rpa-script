"""Electron 应用会话管理 — 裸 CDP（Chrome DevTools Protocol）驱动。

Python 版 Playwright（1.59）无 electron 支持（实测 p.electron 不存在，Electron API
仅 Node.js 版完整），故直接走 CDP：
  - launch：以 --remote-debugging-port=<空闲端口> 启动应用，轮询 /json 就绪；
  - 页面：GET /json 拿 title/url/webSocketDebuggerUrl；
  - 元素：Page 级 WebSocket（websockets 库，全 async）Runtime.evaluate 注入 JS，
    CSS/XPath/text 选择器 → querySelectorAll/document.evaluate，点击/输入/取文本。
供「Electron 应用操作」指令与元素捕获使用。
"""
import asyncio
import json
import logging
import socket
import subprocess
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _selector_js(selector: str) -> str:
    """把 CSS/XPath/text 选择器转成返回首个匹配元素的 JS 表达式（找不到返回 null）。"""
    s = (selector or "").strip()
    if not s:
        return "null"
    low = s.lower()
    if low.startswith("xpath:") or s.startswith("//") or s.startswith("/"):
        xp = s.split(":", 1)[1] if ":" in s else s
        return (f"(()=>{{const r=document.evaluate({json.dumps(xp)},document,null,"
                "XPathResult.FIRST_ORDERED_NODE_TYPE,null);const el=r.singleNodeValue;"
                "return el||null;})()")
    if low.startswith("text:") or low.startswith("text="):
        t = s.split(":", 1)[1] if ":" in s else s.split("=", 1)[1]
        return (f"(()=>{{const els=[...document.querySelectorAll('*')];"
                f"const el=els.find(e=>e.children.length===0&&(e.innerText||'').trim()==={json.dumps(t.strip())});"
                "return el||null;})()")
    return f"document.querySelector({json.dumps(s)})"


class _CDP:
    """单页面 CDP 连接：Runtime.evaluate 等。"""

    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._mid = 0

    async def connect(self):
        if websockets is None:
            raise RuntimeError("缺少 websockets 依赖")
        self._ws = await websockets.connect(self._ws_url, max_size=16 * 1024 * 1024)

    async def call(self, method: str, params: dict | None = None, timeout: float = 10.0):
        self._mid += 1
        mid = self._mid
        await self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == mid:
                return msg
            # 忽略事件消息

    async def evaluate(self, expression: str, timeout: float = 10.0):
        resp = await self.call("Runtime.evaluate",
                               {"expression": expression, "returnByValue": True,
                                "awaitPromise": True}, timeout=timeout)
        if "error" in resp:
            raise RuntimeError(f"CDP error: {resp['error']}")
        result = resp.get("result", {}).get("result", {})
        if result.get("subtype") == "error" or result.get("exceptionDetails"):
            return {"error": str(result.get("description", "JS 异常"))[:300]}
        return result.get("value")

    async def close(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


class ElectronManager:
    """单例：启动/管理 Electron 应用（CDP 驱动）。"""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._port = 0
        self._exe_path = ""
        self._conns: dict[str, _CDP] = {}
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def exe_path(self) -> str:
        return self._exe_path

    @property
    def port(self) -> int:
        return self._port

    # ── 生命周期 ──

    async def launch(self, exe_path: str, args: list[str] | None = None) -> dict:
        async with self._lock:
            if self.is_running:
                return {"error": "Electron 应用已在运行，请先执行「关闭应用」"}
            port = _find_free_port()
            cmd = [exe_path, f"--remote-debugging-port={port}"]
            cmd += [str(a) for a in (args or [])]
            try:
                proc = subprocess.Popen(cmd)
            except Exception as e:
                return {"error": f"Electron 应用启动失败: {e}"}
            self._proc = proc
            self._port = port
            self._exe_path = exe_path
            # 轮询 /json 就绪（应用启动 + 端口监听）
            ready = False
            for _ in range(40):
                if proc.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/json", timeout=0.5) as r:
                        if r.status == 200:
                            ready = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            if not ready:
                await self.close()
                return {"error": "Electron 应用启动超时（CDP 端口未就绪）"}
            await asyncio.sleep(1.0)
            return {"launched": True, "exe": exe_path, "port": port,
                    "pages": await self._list_pages()}

    async def close(self) -> dict:
        async with self._lock:
            for conn in self._conns.values():
                try:
                    await conn.close()
                except Exception:
                    pass
            self._conns.clear()
            proc = self._proc
            self._proc = None
            self._port = 0
            self._exe_path = ""
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            return {"closed": True}

    # ── 页面 ──

    async def _list_pages(self) -> list[dict]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self._port}/json", timeout=2) as r:
                targets = json.loads(r.read())
        except Exception:
            return []
        return [{"title": t.get("title", ""), "url": (t.get("url") or "")[:120],
                 "type": t.get("type", "")}
                for t in targets if t.get("type") == "page"]

    async def pages(self) -> dict:
        if not self.is_running:
            return {"error": "Electron 应用未运行"}
        return {"pages": await self._list_pages()}

    async def _page_target(self, title_fragment: str = "") -> dict | None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self._port}/json", timeout=2) as r:
                targets = json.loads(r.read())
        except Exception:
            return None
        pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            return None
        if title_fragment:
            for t in pages:
                if title_fragment.lower() in (t.get("title") or "").lower():
                    return t
        return pages[0]

    async def _conn_for(self, title_fragment: str = "") -> _CDP | None:
        target = await self._page_target(title_fragment)
        if not target or not target.get("webSocketDebuggerUrl"):
            return None
        url = target["webSocketDebuggerUrl"]
        conn = self._conns.get(url)
        if conn is None:
            conn = _CDP(url)
            try:
                await conn.connect()
            except Exception:
                return None
            self._conns[url] = conn
        return conn

    # ── 元素操作 ──

    async def _eval(self, expression: str, title_fragment: str = ""):
        conn = await self._conn_for(title_fragment)
        if conn is None:
            return {"error": "找不到目标页面（应用未运行或无窗口）"}
        try:
            return await conn.evaluate(expression)
        except Exception as e:
            return {"error": f"CDP 执行失败: {str(e)[:200]}"}

    async def find_elements(self, selector: str, title_fragment: str = "") -> list[dict]:
        low = selector.strip().lower()
        if low.startswith("xpath:") or low.startswith("//"):
            xp = selector.split(":", 1)[1] if ":" in selector else selector
            js = (f"(()=>{{const r=document.evaluate({json.dumps(xp)},"
                  "document,null,XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,null);"
                  "return [...Array(r.snapshotLength)].map((_,i)=>{const el=r.snapshotItem(i);"
                  "return {index:i,text:(el.innerText||'').trim().slice(0,300)}});})()")
        else:
            js = (f"(()=>[...document.querySelectorAll({json.dumps(selector)})].map((el,i)=>"
                  "({index:i,text:(el.innerText||'').trim().slice(0,300)})))()")
        res = await self._eval(js, title_fragment)
        return res if isinstance(res, list) else []

    async def click(self, selector: str, title_fragment: str = "", timeout: int = 5000) -> dict:
        sel = _selector_js(selector)
        js = (f"(()=>{{const el={sel};if(!el)return {{ok:false,error:'元素未找到'}};"
              "el.scrollIntoView({block:'center'});el.click();"
              "return {ok:true,tag:el.tagName,text:(el.innerText||'').trim().slice(0,50)};}})()")
        res = await self._eval(js, title_fragment)
        if isinstance(res, dict) and res.get("ok"):
            return {"clicked": True, "tag": res.get("tag", ""), "text": res.get("text", "")}
        if isinstance(res, dict) and res.get("error"):
            return {"error": res["error"]}
        return {"error": f"点击失败: {res}"}

    async def input_text(self, selector: str, text: str, title_fragment: str = "") -> dict:
        sel = _selector_js(selector)
        # React 兼容：原生 value setter + input/change 事件；contenteditable 用 innerText
        js = (f"(()=>{{const el={sel};if(!el)return {{ok:false,error:'元素未找到'}};"
              "el.focus();"
              "if(el.isContentEditable){el.innerText=" + json.dumps(text) + ";"
              "el.dispatchEvent(new Event('input',{bubbles:true}));"
              "}else{"
              "const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;"
              "const setter=Object.getOwnPropertyDescriptor(proto,'value').set;"
              f"setter.call(el,{json.dumps(text)});"
              "el.dispatchEvent(new Event('input',{bubbles:true}));"
              "el.dispatchEvent(new Event('change',{bubbles:true}));"
              "}return {ok:true};}})()")
        res = await self._eval(js, title_fragment)
        if isinstance(res, dict) and res.get("ok"):
            return {"input_ok": True}
        if isinstance(res, dict) and res.get("error"):
            return {"error": res["error"]}
        return {"error": f"输入失败: {res}"}

    async def get_text(self, selector: str, title_fragment: str = "") -> dict:
        sel = _selector_js(selector)
        js = f"(()=>{{const el={sel};return el?(el.innerText||'').trim():null;}})()"
        res = await self._eval(js, title_fragment)
        if res is None:
            return {"error": "元素未找到"}
        if isinstance(res, dict) and res.get("error"):
            return res
        return {"text": res if isinstance(res, str) else str(res)}

    async def wait_for(self, selector: str, timeout: int = 10000,
                       title_fragment: str = "") -> dict:
        sel = _selector_js(selector)
        js = f"(()=>{{const el={sel};return el?{1}:{0};}})()"
        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            res = await self._eval(js, title_fragment)
            if res == 1:
                return {"found": True}
            if isinstance(res, dict) and res.get("error"):
                return {"found": False, "error": res["error"]}
            await asyncio.sleep(0.3)
        return {"found": False}

    async def eval_js(self, expression: str, title_fragment: str = "") -> dict:
        res = await self._eval(expression, title_fragment)
        return {"value": res}

    # ── 元素捕获（Alt+Click） ──

    async def start_capture(self, title_fragment: str = "", timeout: int = 20) -> dict:
        """注入 alt+click 捕获脚本，阻塞等待用户点选。

        用户 Alt+Click 元素 → 生成选择器返回；Alt+Esc 取消；超时返回错误。
        """
        conn = await self._conn_for(title_fragment)
        if conn is None:
            return {"error": "找不到目标页面（应用未运行或无窗口）"}
        try:
            script = (Path(__file__).resolve().parent / "electron_capture.js")
            js = script.read_text(encoding="utf-8")
        except Exception as e:
            return {"error": f"捕获脚本加载失败: {e}"}
        try:
            await conn.evaluate(js, timeout=5)
        except Exception as e:
            return {"error": f"捕获脚本注入失败: {str(e)[:200]}"}
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(timeout, 1)
        while loop.time() < deadline:
            res = await conn.evaluate(
                "window.__rpaCaptureResult || (window.__rpaCaptureCancelled ? '__cancelled__' : null)",
                timeout=5)
            if res == "__cancelled__":
                return {"cancelled": True}
            if isinstance(res, dict) and res.get("selector"):
                return {"captured": True, "selector": res.get("selector"),
                        "tag": res.get("tag", ""), "text": res.get("text", ""),
                        "cls": res.get("cls", "")}
            await asyncio.sleep(0.3)
        return {"error": "捕获超时"}


# 单例：指令 handler 与捕获器共用
electron_manager = ElectronManager()
