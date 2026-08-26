"""اختبار شامل بدون بريمير وبدون مفتاح API.

يشغّل: سيرفر حقيقي + لوحة وهمية + محاكي بريمير بـ node + رد Claude مُصطنع،
ويتأكد أن الكود يوصل لبريمير وأن نتيجته ترجع للنموذج.

    pip install -r ../server/requirements.txt
    ANTHROPIC_API_KEY=dummy python test_flow.py     (يحتاج node موجود)
"""
import json, subprocess, sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
HOST_JSX = ROOT / "extension" / "jsx" / "host.jsx"
FAKE = Path(__file__).parent / "fake_premiere.js"

import agent as agent_mod
from fastapi.testclient import TestClient


class Block:
    def __init__(self, **kw): self.__dict__.update(kw)

class Resp:
    def __init__(self, content, stop_reason): self.content, self.stop_reason = content, stop_reason

SCRIPT = [
    Resp([Block(type="text", text="خلني أشوف التايم لاين أول."),
          Block(type="tool_use", id="t1", name="get_premiere_state", input={"deep": True})], "tool_use"),
    Resp([Block(type="tool_use", id="t2", name="run_premiere_script",
                input={"code": 'AI.addMarker(3,"مشهد 1","");', "purpose": "إضافة ماركر"})], "tool_use"),
    Resp([Block(type="text", text="زين، حطيت ماركر بالثانية 3.")], "end_turn"),
]

calls = []

class FakeMessages:
    async def create(self, **kw):
        calls.append(kw)
        return SCRIPT[len(calls) - 1]

class FakeClient:
    messages = FakeMessages()

agent_mod.PremiereAgent._get_client = lambda self: FakeClient()

import app as app_mod  # noqa: E402

def run_in_premiere(code: str) -> dict:
    out = subprocess.run(["node", str(FAKE), str(HOST_JSX)], input=code,
                         capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        return {"ok": False, "error": out.stderr[:300]}
    return json.loads(out.stdout)

with TestClient(app_mod.app) as client:
    with client.websocket_connect("/ws/panel") as ws:
        ws.send_json({"type": "hello", "host": "PPRO 25.1", "premiere": {"project": "Test.prproj"}})
        ws.send_json({"type": "user_message", "text": "حط ماركر بالثانية 3"})

        seen, execs = [], 0
        for _ in range(20):
            msg = ws.receive_json()
            seen.append(msg["type"])
            if msg["type"] == "exec":
                execs += 1
                res = run_in_premiere(msg["code"])
                print(f"  ← نفّذ: {msg['code'][:60]!r} → ok={res.get('ok')}")
                ws.send_json({"type": "exec_result", "id": msg["id"], **res})
            elif msg["type"] == "assistant":
                print(f"  ← رد: {msg['text']}")
                if "ماركر بالثانية" in msg["text"]:
                    break
            elif msg["type"] == "error":
                print("  ← خطأ:", msg["text"]); break

print("\nترتيب الرسائل:", seen)
assert execs == 2, f"توقعنا تنفيذين، صار {execs}"
assert seen[-1] == "assistant"
# التحقق أن نتائج بريمير رجعت للنموذج بشكل صحيح
history = calls[-1]["messages"]           # نفس القائمة (مرجع) بعد انتهاء الحلقة
tool_results = [m for m in history
                if m["role"] == "user" and isinstance(m["content"], list)]
assert len(tool_results) == 2, [m["role"] for m in history]
payload = json.loads(tool_results[-1]["content"][0]["content"])
assert payload["ok"] is True, payload
state_payload = json.loads(tool_results[0]["content"][0]["content"])
assert state_payload["result"]["projectName"] == "Test.prproj"
assert state_payload["result"]["activeSequence"]["fps"] == 25
print("نتيجة أداة الحالة وصلت للنموذج ✅")
print("عدد نداءات Claude:", len(calls), "| أدوات مُعرَّفة:", [t["name"] for t in calls[0]["tools"]])
print("\n✅ نجح الاختبار الشامل")
