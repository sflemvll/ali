import os
import re
import time
import uuid
import asyncio
import tempfile
import threading
import requests as req_lib
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from pydantic import BaseModel
import yt_dlp

# ── Invidious instances للـ YouTube fallback ─────────────────────────
INVIDIOUS = [
    "https://inv.nadeko.net",
    "https://invidious.privacydev.net",
    "https://yt.cdaut.de",
    "https://invidious.nerdvpn.de",
]

def _yt_id(url: str):
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None

def _invidious_info(video_id: str):
    for inst in INVIDIOUS:
        try:
            r = req_lib.get(f"{inst}/api/v1/videos/{video_id}", timeout=8)
            if r.status_code == 200:
                return r.json(), inst
        except Exception:
            continue
    return None, None

def _invidious_stream_url(video_id: str, height: int = 0):
    """احصل على رابط stream مدمج (فيديو+صوت) من Invidious"""
    data, inst = _invidious_info(video_id)
    if not data:
        return None, None, None
    title = data.get("title", "video")
    # formatStreams = فيديو+صوت مدمج (يصل حتى 720p) — يشتغل مباشرة
    fmt_streams = data.get("formatStreams", [])
    if fmt_streams:
        if height:
            candidates = [
                s for s in fmt_streams
                if int(s.get("resolution","0p").replace("p","") or 0) <= height
            ]
            if candidates:
                candidates.sort(
                    key=lambda x: int(x.get("resolution","0p").replace("p","") or 0),
                    reverse=True
                )
                return candidates[0].get("url"), title, inst
        # أعلى جودة متاحة
        fmt_streams.sort(
            key=lambda x: int(x.get("resolution","0p").replace("p","") or 0),
            reverse=True
        )
        return fmt_streams[0].get("url"), title, inst
    return None, None, None

app = FastAPI(title="SaveIt — Universal Video Downloader")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── مجلدات ──────────────────────────────────────────────────────────
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "saveit_downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ── نماذج البيانات ──────────────────────────────────────────────────
class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    quality: str

# ── Cache معلومات الفيديو (في الذاكرة) ─────────────────────────────
_info_cache: dict = {}   # url -> {"data": ..., "ts": float}
CACHE_TTL = 3600         # ساعة واحدة

def cache_get(url: str):
    entry = _info_cache.get(url)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None

def cache_set(url: str, data: dict):
    _info_cache[url] = {"data": data, "ts": time.time()}

# ── مخزن مهام التحميل ───────────────────────────────────────────────
# job_id -> {status, percent, speed, downloaded, total, filepath, error}
_jobs: dict = {}

# ── اكتشاف المنصة ───────────────────────────────────────────────────
def detect_platform(url: str) -> str:
    url = url.lower()
    for domain, name in [
        ("youtube.com","YouTube"),("youtu.be","YouTube"),
        ("instagram.com","Instagram"),
        ("tiktok.com","TikTok"),
        ("twitter.com","Twitter/X"),("x.com","Twitter/X"),
        ("facebook.com","Facebook"),("fb.watch","Facebook"),
        ("reddit.com","Reddit"),("twitch.tv","Twitch"),
        ("dailymotion.com","Dailymotion"),("vimeo.com","Vimeo"),
        ("pinterest.com","Pinterest"),("snapchat.com","Snapchat"),
        ("linkedin.com","LinkedIn"),
    ]:
        if domain in url:
            return name
    return "Unknown"

# ── إعدادات yt-dlp الأساسية ─────────────────────────────────────────
COOKIES_FILE = Path(__file__).parent / "cookies.txt"

def _ensure_cookies_file():
    """إذا في YOUTUBE_COOKIES في البيئة، اكتبها لملف مؤقت"""
    cookie_env = os.environ.get("YOUTUBE_COOKIES", "")
    if cookie_env:
        # Railway يخزن السطور كـ \n نصية — نحولها لأسطر حقيقية
        content = cookie_env.replace("\\n", "\n").replace("\\t", "\t")
        COOKIES_FILE.write_text(content, encoding="utf-8")

def base_opts(for_download: bool = False) -> dict:
    _ensure_cookies_file()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        },
    }
    # استخدم tv_embedded — يعمل بدون PO token
    if for_download:
        opts["extractor_args"] = {
            "youtube": {"player_client": ["tv_embedded", "ios"]}
        }
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    return opts

# ── تشخيص الكوكيز ───────────────────────────────────────────────────
@app.get("/debug/cookies")
async def debug_cookies():
    _ensure_cookies_file()
    env_val = os.environ.get("YOUTUBE_COOKIES", "")
    exists  = COOKIES_FILE.exists()
    size    = COOKIES_FILE.stat().st_size if exists else 0
    lines   = COOKIES_FILE.read_text(encoding="utf-8").count("\n") if exists else 0
    return {
        "env_set":     bool(env_val),
        "env_len":     len(env_val),
        "file_exists": exists,
        "file_size":   size,
        "file_lines":  lines,
        "file_path":   str(COOKIES_FILE),
    }

# ── تنظيف اسم الملف ─────────────────────────────────────────────────
def clean(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", name or "video").strip()

# ────────────────────────────────────────────────────────────────────
# الصفحة الرئيسية
# ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/manifest.json")
async def manifest():
    return FileResponse("static/manifest.json", media_type="application/json")

@app.get("/sw.js")
async def sw():
    return FileResponse("static/sw.js", media_type="application/javascript")

@app.get("/sitemap.xml")
async def sitemap():
    return FileResponse("templates/sitemap.xml", media_type="application/xml")

@app.get("/robots.txt")
async def robots():
    return FileResponse("robots.txt", media_type="text/plain")

# ────────────────────────────────────────────────────────────────────
# API — جلب معلومات الفيديو (مع Cache)
# ────────────────────────────────────────────────────────────────────
@app.post("/api/info")
async def get_info(data: InfoRequest):
    # تحقق من الكاش أولاً
    cached = cache_get(data.url)
    if cached:
        return {**cached, "cached": True}

    try:
        with yt_dlp.YoutubeDL({**base_opts(), "extract_flat": False}) as ydl:
            info = ydl.extract_info(data.url, download=False)

        formats = info.get("formats", [])
        qualities, seen = [], set()
        for f in formats:
            h = f.get("height")
            if h and f.get("ext") in ("mp4","webm","mov") and f.get("vcodec") not in ("none",None):
                lbl = f"{h}p"
                if lbl not in seen:
                    seen.add(lbl)
                    qualities.append({"label": lbl, "height": h})
        qualities.sort(key=lambda x: x["height"], reverse=True)

        result = {
            "title":      info.get("title") or info.get("description","")[:80] or "بدون عنوان",
            "thumbnail":  info.get("thumbnail",""),
            "duration":   info.get("duration", 0),
            "channel":    info.get("uploader") or info.get("channel",""),
            "view_count": info.get("view_count", 0),
            "platform":   detect_platform(data.url),
            "qualities":  qualities,
            "cached":     False,
        }
        cache_set(data.url, result)
        return result

    except Exception as e:
        err = str(e)
        # ── fallback: Invidious لـ YouTube ──────────────────────────
        vid = _yt_id(data.url)
        if vid:
            inv_data, inst = _invidious_info(vid)
            if inv_data:
                streams = inv_data.get("adaptiveFormats", []) + inv_data.get("formatStreams", [])
                qualities, seen = [], set()
                for s in streams:
                    res = s.get("resolution","")
                    if res and s.get("type","").startswith("video"):
                        h = int(res.replace("p","") or 0)
                        lbl = f"{h}p"
                        if lbl not in seen and h:
                            seen.add(lbl)
                            qualities.append({"label": lbl, "height": h})
                qualities.sort(key=lambda x: x["height"], reverse=True)
                if not qualities:
                    qualities = [{"label": "best", "height": 0}]
                result = {
                    "title":      inv_data.get("title","بدون عنوان"),
                    "thumbnail":  (inv_data.get("videoThumbnails") or [{}])[0].get("url",""),
                    "duration":   inv_data.get("lengthSeconds", 0),
                    "channel":    inv_data.get("author",""),
                    "view_count": inv_data.get("viewCount", 0),
                    "platform":   "YouTube",
                    "qualities":  qualities,
                    "cached":     False,
                    "via_invidious": True,
                }
                cache_set(data.url, result)
                return result
        # إذا ما نفع أي شي
        if "sign in" in err.lower() or "login" in err.lower():
            raise HTTPException(401, "هذا المحتوى يحتاج تسجيل دخول")
        if "private" in err.lower():
            raise HTTPException(403, "المحتوى خاص")
        raise HTTPException(400, f"تعذّر جلب المعلومات: {err}")

# ────────────────────────────────────────────────────────────────────
# API — بدء التحميل (يرجع job_id فوراً)
# ────────────────────────────────────────────────────────────────────
@app.post("/api/download/start")
async def download_start(data: DownloadRequest):
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "status": "pending",
        "percent": 0,
        "speed": 0,
        "downloaded": 0,
        "total": 0,
        "filepath": None,
        "filename": "video",
        "ext": "mp4",
        "error": None,
    }
    # شغّل التحميل في thread منفصل
    t = threading.Thread(target=_run_download, args=(job_id, data.url, data.quality), daemon=True)
    t.start()
    return {"job_id": job_id}

def _run_download(job_id: str, url: str, quality: str):
    job = _jobs[job_id]
    job["status"] = "downloading"

    # ── progress hook ──────────────────────────────────────────
    # نتتبع مجموع ما تم تحميله من كل الستريمات (فيديو + صوت)
    _downloaded_sum = [0]
    _total_sum      = [0]
    _streams_seen   = set()

    def hook(d):
        if d["status"] == "downloading":
            fid = d.get("info_dict", {}).get("format_id", id(d))
            dl  = d.get("downloaded_bytes", 0) or 0
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            spd = d.get("speed") or 0

            # سجّل حجم كل ستريم مرة واحدة
            if fid not in _streams_seen and tot:
                _streams_seen.add(fid)
                _total_sum[0] += tot

            _downloaded_sum[0] = max(_downloaded_sum[0], dl) if len(_streams_seen) <= 1 else _downloaded_sum[0]
            # مجموع حقيقي: نأخذ downloaded_bytes من الهوك مباشرة
            _downloaded_sum[0] = dl

            total = _total_sum[0] or tot
            pct   = (dl / total * 100) if total else 0
            job.update({
                "percent":    round(min(pct, 98), 1),
                "speed":      spd,
                "downloaded": dl,
                "total":      total,
            })
        elif d["status"] == "finished":
            job["status"]  = "processing"
            job["percent"] = 99

    # ── إعدادات الصيغة ────────────────────────────────────────
    if quality == "audio":
        fmt, ext = "bestaudio*/best", "mp3"
        pp = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
    elif quality == "best":
        fmt, ext = "bestvideo*+bestaudio*/best", "mp4"
        pp = [{"key":"FFmpegVideoConvertor","preferedformat":"mp4"}]
    else:
        h   = quality.replace("p","")
        fmt = f"bestvideo*[height<={h}]+bestaudio*/best[height<={h}]/best"
        ext = "mp4"
        pp  = [{"key":"FFmpegVideoConvertor","preferedformat":"mp4"}]

    uid      = job_id
    out_tmpl = str(DOWNLOAD_DIR / f"{uid}_%(title)s.%(ext)s")

    opts = {
        **base_opts(for_download=True),
        "format": fmt,
        "outtmpl": out_tmpl,
        "postprocessors": pp,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = clean(info.get("title","video"))

        # البحث عن الملف
        found = None
        for f in DOWNLOAD_DIR.iterdir():
            if uid in f.name and f.suffix in (".mp4",".mp3",".webm",".m4a",".mov"):
                found = f
                break

        if not found:
            job["status"]  = "error"
            job["error"]   = "لم يتم إيجاد الملف بعد التحميل"
            return

        # ✅ الحجم الحقيقي للملف النهائي بعد الدمج
        real_size = found.stat().st_size

        job.update({
            "status":     "done",
            "percent":    100,
            "filepath":   str(found),
            "filename":   f"{title}.{ext}",
            "ext":        ext,
            "downloaded": real_size,   # الحجم الفعلي
            "total":      real_size,   # يطابق = 100%
        })

    except Exception as e:
        err_msg = str(e)
        # ── fallback: Invidious لـ YouTube ──────────────────────────
        vid = _yt_id(url)
        if vid:
            try:
                h_val = int(quality.replace("p","")) if quality not in ("best","audio") else 0
                stream_url, title_inv, _ = _invidious_stream_url(vid, h_val)
                if stream_url:
                    title_inv = clean(title_inv or "video")
                    out_path  = DOWNLOAD_DIR / f"{job_id}_{title_inv}.mp4"
                    job.update({"status":"downloading","percent":1})
                    # تحميل مباشر مع progress
                    with req_lib.get(stream_url, stream=True, timeout=60) as resp:
                        total = int(resp.headers.get("content-length", 0))
                        dl = 0
                        with open(out_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=1024*256):
                                f.write(chunk)
                                dl += len(chunk)
                                pct = (dl/total*100) if total else 50
                                job.update({"percent": round(min(pct,98),1),
                                            "downloaded": dl, "total": total,
                                            "speed": 0})
                    real_size = out_path.stat().st_size
                    job.update({
                        "status": "done", "percent": 100,
                        "filepath": str(out_path),
                        "filename": f"{title_inv}.mp4",
                        "ext": "mp4",
                        "downloaded": real_size,
                        "total": real_size,
                    })
                    return
            except Exception as inv_e:
                err_msg = f"yt-dlp: {err_msg} | invidious: {inv_e}"
        job["status"] = "error"
        job["error"]  = err_msg

# ────────────────────────────────────────────────────────────────────
# API — SSE: بث التقدم الحقيقي
# ────────────────────────────────────────────────────────────────────
@app.get("/api/progress/{job_id}")
async def progress_stream(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(404, "المهمة غير موجودة")

    async def event_gen():
        import json
        while True:
            job = _jobs.get(job_id, {})
            payload = json.dumps({
                "status":     job.get("status","pending"),
                "percent":    job.get("percent", 0),
                "speed":      job.get("speed", 0),
                "downloaded": job.get("downloaded", 0),
                "total":      job.get("total", 0),
                "error":      job.get("error"),
            })
            yield f"data: {payload}\n\n"

            st = job.get("status","pending")
            if st in ("done","error"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"},
    )

# ────────────────────────────────────────────────────────────────────
# API — تسليم الملف بعد اكتمال التحميل
# ────────────────────────────────────────────────────────────────────
@app.get("/api/file/{job_id}")
async def get_file(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "المهمة غير موجودة")
    if job["status"] != "done":
        raise HTTPException(400, "الملف غير جاهز بعد")

    fp   = Path(job["filepath"])
    ext  = job["ext"]
    name = job["filename"]

    if not fp.exists():
        raise HTTPException(410, "انتهت صلاحية الملف")

    media_type = "audio/mpeg" if ext == "mp3" else "video/mp4"
    encoded    = quote(name, safe="")
    disposition = f'attachment; filename="video.{ext}"; filename*=UTF-8\'\'{encoded}'

    def stream():
        with open(fp, "rb") as f:
            yield from f
        fp.unlink(missing_ok=True)
        _jobs.pop(job_id, None)

    return StreamingResponse(stream(), media_type=media_type,
                             headers={"Content-Disposition": disposition})

# ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
