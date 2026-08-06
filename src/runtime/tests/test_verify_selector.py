"""
End-to-end tests for verify-selector cross-browser fan-out.

The extension manager is a process-global singleton; tests populate it with
fake connections and drive responses through ext_manager.dispatch() the same
way the real extension background reports verifySelectorResult.
"""

import asyncio

from src.runtime.websocket_manager import ext_manager
from src.runtime.routers.extension_router import verify_selector


class FakeConn:
    def __init__(self, cid, browser):
        self.client_id = cid
        self.browser = browser
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)


def _run(coro):
    try:
        return asyncio.run(coro)
    finally:
        ext_manager._connections.clear()


def test_verify_selector_no_connections():
    async def scenario():
        return await verify_selector({"selector": "button.x", "requestId": "r0"})

    res = _run(scenario())
    assert res["error"] == "没有浏览器扩展连接"


def test_verify_selector_fanout_first_found_wins():
    async def scenario():
        c1 = FakeConn("c1", "chrome")
        c2 = FakeConn("c2", "edge")
        ext_manager._connections["c1"] = c1
        ext_manager._connections["c2"] = c2

        async def responder():
            await asyncio.sleep(0.05)
            # edge (c2) reports found
            await ext_manager.dispatch("verifySelectorResult", {
                "requestId": "r1",
                "result": {"found": True, "count": 3, "visible": 2, "invisible": 1,
                           "tabUrl": "https://example.com", "tabTitle": "示例"},
            }, "c2")

        t = asyncio.ensure_future(responder())
        res = await verify_selector({"selector": "button.x", "requestId": "r1"})
        await t
        return res, c1, c2

    res, c1, c2 = _run(scenario())
    assert res["found"] is True
    assert res["count"] == 3
    assert res["visible"] == 2
    assert res["invisible"] == 1
    assert res["browser"] == "edge"           # fan-out tagged the responding browser
    assert res["tabUrl"] == "https://example.com"
    # both browsers received the request
    assert len(c1.sent) == 1 and len(c2.sent) == 1
    assert c1.sent[0]["action"] == "verifySelector"


def test_verify_selector_fanout_all_miss_aggregates_scanned():
    async def scenario():
        ext_manager._connections["c1"] = FakeConn("c1", "chrome")
        ext_manager._connections["c2"] = FakeConn("c2", "edge")

        async def responder():
            await asyncio.sleep(0.05)
            await ext_manager.dispatch("verifySelectorResult", {
                "requestId": "r2",
                "result": {"found": False, "count": 0, "visible": 0, "invisible": 0,
                           "scanned": [{"tabUrl": "https://a.com", "tabTitle": "A",
                                       "count": 1, "visible": 0, "invisible": 1}]},
            }, "c1")
            await asyncio.sleep(0.05)
            await ext_manager.dispatch("verifySelectorResult", {
                "requestId": "r2",
                "result": {"found": False, "count": 0, "visible": 0, "invisible": 0,
                           "scanned": [{"tabUrl": "https://b.com", "tabTitle": "B",
                                       "count": 0, "visible": 0, "invisible": 0}]},
            }, "c2")

        t = asyncio.ensure_future(responder())
        res = await verify_selector({"selector": "button.x", "requestId": "r2"})
        await t
        return res

    res = _run(scenario())
    assert res["found"] is False
    assert len(res["scanned"]) == 2
    urls = {s["tabUrl"] for s in res["scanned"]}
    assert urls == {"https://a.com", "https://b.com"}
    browsers = {s["browser"] for s in res["scanned"]}
    assert browsers == {"chrome", "edge"}
