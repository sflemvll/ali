"""جسر التخاطب مع لوحة بريمير عبر WebSocket.

السيرفر يرسل كود ExtendScript إلى اللوحة، واللوحة تنفّذه داخل بريمير وترجع النتيجة.
كل طلب تنفيذ يحمل معرّفاً فريداً حتى تُربط النتيجة بطلبها.
"""

import asyncio
import uuid
from typing import Any, Dict


class PanelDisconnected(Exception):
    """اللوحة غير متصلة أو انقطعت أثناء التنفيذ."""


class PanelBridge:
    def __init__(self, websocket, exec_timeout: float = 180.0):
        self.ws = websocket
        self.exec_timeout = exec_timeout
        self._pending: Dict[str, asyncio.Future] = {}
        self._closed = False

    # ── من السيرفر إلى اللوحة ───────────────────────────────────────
    async def send(self, payload: dict) -> None:
        if self._closed:
            raise PanelDisconnected("اللوحة غير متصلة.")
        await self.ws.send_json(payload)

    async def run_script(self, code: str, purpose: str = "") -> dict:
        """يرسل الكود للوحة وينتظر نتيجة تنفيذه داخل بريمير."""
        req_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[req_id] = future

        try:
            await self.send({"type": "exec", "id": req_id, "code": code, "purpose": purpose})
            return await asyncio.wait_for(future, timeout=self.exec_timeout)
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": (
                    f"انتهت المهلة ({int(self.exec_timeout)} ثانية) بدون رد من بريمير. "
                    "غالباً العملية طويلة جداً أو بريمير يعرض نافذة تنتظر المستخدم."
                ),
            }
        finally:
            self._pending.pop(req_id, None)

    # ── من اللوحة إلى السيرفر ───────────────────────────────────────
    def resolve(self, message: dict) -> None:
        future = self._pending.get(message.get("id", ""))
        if future is None or future.done():
            return
        future.set_result(
            {
                "ok": bool(message.get("ok")),
                "data": message.get("data"),
                "error": message.get("error"),
            }
        )

    def close(self) -> None:
        self._closed = True
        for future in self._pending.values():
            if not future.done():
                future.set_exception(PanelDisconnected("انقطع الاتصال باللوحة أثناء التنفيذ."))
        self._pending.clear()
