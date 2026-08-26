"""حلقة الذكاء: تحوّل طلب المستخدم بالعربية إلى أوامر تُنفَّذ داخل Adobe Premiere Pro."""

import json
import os
from typing import Any, List

import anthropic

from bridge import PanelBridge, PanelDisconnected
from prompts import SYSTEM_PROMPT, TOOLS

MODEL = os.environ.get("PREMIERE_AI_MODEL", "claude-opus-5")
MAX_TOKENS = 16000
MAX_ITERATIONS = int(os.environ.get("PREMIERE_AI_MAX_STEPS", "16"))
MAX_RESULT_CHARS = 20000
MAX_HISTORY_TURNS = 40


def _truncate(text: str) -> str:
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + f"\n… [تم اختصار النتيجة، الحجم الأصلي {len(text)} حرفاً]"


class PremiereAgent:
    """محادثة واحدة مرتبطة بلوحة بريمير واحدة."""

    def __init__(self, bridge: PanelBridge):
        # نستخدم حلقة أدوات يدوية (بدل tool_runner) لأن تنفيذ الأدوات يمرّ عبر
        # WebSocket إلى بريمير، ونريد بثّ حالة كل خطوة إلى اللوحة أثناء التنفيذ.
        self.bridge = bridge
        self.messages: List[dict] = []
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        """ننشئ العميل عند أول استخدام حتى لا ينهار الاتصال إذا كان المفتاح ناقصاً."""
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        return self._client

    def reset(self) -> None:
        self.messages = []

    def _trim_history(self) -> None:
        if len(self.messages) > MAX_HISTORY_TURNS:
            # نحذف من البداية مع الحفاظ على أن أول رسالة دور "user"
            drop = len(self.messages) - MAX_HISTORY_TURNS
            self.messages = self.messages[drop:]
            while self.messages and self.messages[0].get("role") != "user":
                self.messages.pop(0)

    # ── تنفيذ أداة واحدة داخل بريمير ─────────────────────────────────
    async def _run_tool(self, name: str, tool_input: dict) -> str:
        if name == "get_premiere_state":
            deep = tool_input.get("deep", True)
            code = f"AI.state({json.dumps(bool(deep))})"
            purpose = "قراءة حالة المشروع والتايم لاين"
        elif name == "run_premiere_script":
            code = tool_input.get("code", "")
            purpose = tool_input.get("purpose", "") or "تنفيذ أمر داخل بريمير"
        else:
            return json.dumps({"ok": False, "error": f"أداة غير معروفة: {name}"}, ensure_ascii=False)

        await self.bridge.send({"type": "status", "text": purpose})
        result = await self.bridge.run_script(code, purpose)

        if result.get("ok"):
            payload = {"ok": True, "result": result.get("data")}
        else:
            payload = {"ok": False, "error": result.get("error") or "خطأ غير معروف داخل بريمير"}
        return _truncate(json.dumps(payload, ensure_ascii=False))

    # ── الحلقة الرئيسية ──────────────────────────────────────────────
    async def handle(self, user_text: str) -> None:
        self.messages.append({"role": "user", "content": user_text})
        self._trim_history()

        for step in range(MAX_ITERATIONS):
            try:
                response = await self._get_client().messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=[
                        {
                            "type": "text",
                            "text": SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    thinking={"type": "adaptive"},
                    output_config={"effort": "high"},
                    tools=TOOLS,
                    messages=self.messages,
                )
            except anthropic.AuthenticationError:
                await self._fail(
                    "مفتاح ANTHROPIC_API_KEY غير صالح. تأكد منه في ملف .env جنب السيرفر."
                )
                return
            except anthropic.RateLimitError:
                await self._fail("وصلنا حد الطلبات على المفتاح. انتظر شوية وجرّب مرة ثانية.")
                return
            except anthropic.APIConnectionError:
                await self._fail("ما گدرت أوصل لخوادم Claude. تأكد من الإنترنت.")
                return
            except anthropic.APIStatusError as e:
                await self._fail(f"خطأ من واجهة Claude ({e.status_code}): {e.message}")
                return
            except (TypeError, anthropic.AnthropicError) as e:
                # أشهر حالة: المفتاح غير موجود أصلاً
                await self._fail(f"ما گدرت أرسل الطلب لـ Claude: {e}")
                return

            if response.stop_reason == "refusal":
                await self._fail("الطلب انرفض من طرف نموذج الأمان. جرّب تصيغه بشكل ثاني.")
                return

            self.messages.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                text = "\n".join(b.text for b in response.content if b.type == "text").strip()
                await self.bridge.send({"type": "assistant", "text": text or "تم."})
                return

            # نعرض للمستخدم أي كلام قاله النموذج قبل استدعاء الأدوات
            preface = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if preface:
                await self.bridge.send({"type": "assistant", "text": preface})

            results = []
            for tool in tool_uses:
                try:
                    output = await self._run_tool(tool.name, tool.input)
                except PanelDisconnected as e:
                    await self._fail(str(e))
                    return
                results.append(
                    {"type": "tool_result", "tool_use_id": tool.id, "content": output}
                )
            self.messages.append({"role": "user", "content": results})

        await self._fail(
            f"وقفت بعد {MAX_ITERATIONS} خطوة بدون ما أخلّص الطلب. جرّب تقسّم الطلب لخطوات أصغر."
        )

    async def _fail(self, text: str) -> None:
        try:
            await self.bridge.send({"type": "error", "text": text})
        except PanelDisconnected:
            print(f"[agent] تعذّر إبلاغ اللوحة (منقطعة): {text}")
