"""سيرفر محلي يربط لوحة Adobe Premiere Pro بـ Claude.

التشغيل:
    pip install -r requirements.txt
    python app.py            (أو: uvicorn app:app --host 127.0.0.1 --port 8777)

المفتاح يُقرأ من متغيّر البيئة ANTHROPIC_API_KEY أو من ملف .env بجانب هذا الملف.
"""

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# تحميل .env البسيط (بدون اعتماديات إضافية)
ENV_FILE = Path(__file__).with_name(".env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from agent import MODEL, PremiereAgent  # noqa: E402  (بعد تحميل .env)
from bridge import PanelBridge  # noqa: E402

HOST = os.environ.get("PREMIERE_AI_HOST", "127.0.0.1")
PORT = int(os.environ.get("PREMIERE_AI_PORT", "8777"))

app = FastAPI(title="Premiere AI Bridge")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    key_state = "موجود ✅" if os.environ.get("ANTHROPIC_API_KEY") else "مفقود ❌"
    return f"""<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">
<title>Premiere AI Bridge</title>
<body style="font-family:sans-serif;background:#1e1e1e;color:#eee;padding:24px">
<h2>سيرفر مساعد بريمير يشتغل ✅</h2>
<p>المفتاح ANTHROPIC_API_KEY: {key_state}</p>
<p>النموذج: <code>{MODEL}</code></p>
<p>عنوان اللوحة: <code>ws://{HOST}:{PORT}/ws/panel</code></p>
<p>افتح بريمير ثم: <b>Window → Extensions → مساعد الذكاء الاصطناعي</b></p>
</body></html>"""


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "model": MODEL,
        "api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.websocket("/ws/panel")
async def panel_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    bridge = PanelBridge(websocket)
    agent = PremiereAgent(bridge)
    task: asyncio.Task | None = None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        await websocket.send_json(
            {
                "type": "error",
                "text": "ما لكيت ANTHROPIC_API_KEY. سوّي ملف .env جنب app.py وحط بيه: ANTHROPIC_API_KEY=sk-ant-...",
            }
        )

    try:
        while True:
            message = await websocket.receive_json()
            kind = message.get("type")

            if kind == "hello":
                info = message.get("premiere") or {}
                project = info.get("project") or "بدون مشروع مفتوح"
                print(f"[panel] متصل: {message.get('host')} — {project}")

            elif kind == "user_message":
                if task and not task.done():
                    await websocket.send_json(
                        {"type": "error", "text": "أكو طلب قيد التنفيذ حالياً. انتظر يخلص."}
                    )
                    continue
                task = asyncio.create_task(agent.handle(message.get("text", "")))

            elif kind == "exec_result":
                bridge.resolve(message)

            elif kind == "reset":
                agent.reset()
                await websocket.send_json({"type": "reset_ok"})

    except WebSocketDisconnect:
        print("[panel] انقطع الاتصال")
    finally:
        bridge.close()
        if task and not task.done():
            task.cancel()


if __name__ == "__main__":
    import uvicorn

    print(f"→ السيرفر يشتغل على http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
