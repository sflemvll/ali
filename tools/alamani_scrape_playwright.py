#!/usr/bin/env python3
"""نسخة المتصفح من السحب (Playwright) — بديل عن alamani_scrape.py.

استعملها إذا تغيّرت واجهة الـ API أو صار الوصول المباشر محجوبًا.
السكربت يفتح الصفحة بمتصفح حقيقي، يسكرول للأسفل حتى تنتهي القائمة،
ويلتقط بيانات المنتجات من ردود JSON التي يطلبها الموقع نفسه
(list_view و list_view_materials) بدل الاعتماد على شكل الـ HTML.

التنصيب مرة واحدة:
    pip install playwright
    playwright install chromium

الاستعمال:
    python3 tools/alamani_scrape_playwright.py
    python3 tools/alamani_scrape_playwright.py --url https://alamani.iq/computer/list_view/7
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re

from playwright.async_api import async_playwright

DEFAULT_URL = "https://alamani.iq/computer/list_view/11"
SCROLL_PAUSE = 1.2          # ثانية بين كل سكرول وآخر (تفاديًا للحظر)
MAX_IDLE_ROUNDS = 4         # نتوقف بعد أربع دورات بلا منتجات جديدة


def price_min(raw: str) -> int:
    nums = re.findall(r"[\d,]{4,}", raw or "")
    return int(nums[0].replace(",", "")) if nums else 0


async def scrape(url: str, out: str, headless: bool) -> int:
    model = url.rstrip("/").split("/")[-3] if "/list_view/" in url else "computer"
    products: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        page = await browser.new_page()

        async def on_response(resp):
            if "/api_app/list_view" not in resp.url:
                return
            try:
                data = await resp.json()
            except Exception:                                  # noqa: BLE001
                return
            cards = data.get("card") if isinstance(data, dict) else data
            for c in cards or []:
                if not isinstance(c, dict) or "id" not in c:
                    continue
                pid = str(c["id"])
                products.setdefault(pid, {
                    "id": pid,
                    "title": (c.get("title") or "").strip(),
                    "price_iqd": price_min(c.get("price", "")),
                    "price_raw": (c.get("price") or "").strip(),
                    "price_usd": round(float(c.get("price_dollars") or 0), 2),
                    "specs": " ".join((c.get("description") or "").split()),
                    "code": c.get("code", ""),
                    "id_cat": c.get("id_cat", ""),
                    "url": f"https://alamani.iq/{c.get('model') or model}/details/{pid}",
                    "image": c.get("image", ""),
                    "source_cat": url,
                })

        page.on("response", on_response)
        await page.goto(url, wait_until="networkidle", timeout=90_000)

        idle = 0
        while idle < MAX_IDLE_ROUNDS:
            before = len(products)
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(int(SCROLL_PAUSE * 1000))
            idle = idle + 1 if len(products) == before else 0
            print(f"  ... {len(products)} منتج", flush=True)

        await browser.close()

    rows = sorted(products.values(), key=lambda r: r["price_iqd"])
    if not rows:
        print("لم يُلتقط أي منتج — راجع الرابط أو شغّل السكربت بـ --headed للمراقبة")
        return 1
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"تم حفظ {len(rows)} منتج في {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--out", default="laptops.csv")
    ap.add_argument("--headed", action="store_true", help="تشغيل المتصفح مرئيًا")
    args = ap.parse_args()
    return asyncio.run(scrape(args.url, args.out, headless=not args.headed))


if __name__ == "__main__":
    raise SystemExit(main())
