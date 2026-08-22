#!/usr/bin/env python3
"""سحب قائمة المنتجات من موقع الأماني (alamani.iq).

الموقع تطبيق Nuxt يقرأ بياناته من واجهة JSON، فبدل تشغيل متصفح
نستدعي نفس الواجهة التي يستدعيها الموقع:

    POST https://apiapp.alamani.iq/api_app/list_view
         {model, id_cat, id_cust, order}
      -> card[]        أول دفعة منتجات
         id_cat{}      الأقسام الفرعية
         id_material   بقية معرفات المنتجات مفصولة بفواصل

    POST https://apiapp.alamani.iq/api_app/list_view_materials
         {model, id_cat, id_material, type_view, order, min, max, characteristic, id_cust}
      -> [ ...المنتجات ]

الاستعمال:
    python3 tools/alamani_scrape.py                      # اللابتوبات المستعملة + الجديدة
    python3 tools/alamani_scrape.py --cat computer:11    # قسم واحد
    python3 tools/alamani_scrape.py --out laptops.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.request

API = "https://apiapp.alamani.iq/api_app"
BATCH = 8          # نفس حجم الدفعة الذي يستعمله الموقع
DELAY = 1.0        # ثانية بين الطلبات، تفاديًا للحظر
TIMEOUT = 60

# الأقسام الافتراضية: لابتوبات مستعملة، ولابتوبات جديدة
DEFAULT_CATS = [("computer", 11), ("computer", 7)]


def post(path: str, payload: dict) -> object:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}/{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://alamani.iq",
            "Referer": "https://alamani.iq/",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def price_min(raw: str) -> int:
    """يحوّل "378,844 - 392,058" إلى 378844 (الحد الأدنى = سعر النقد)."""
    nums = re.findall(r"[\d,]{4,}", raw or "")
    if not nums:
        return 0
    return int(nums[0].replace(",", ""))


def normalize(card: dict, model: str, root_cat: int) -> dict:
    pid = str(card.get("id", ""))
    return {
        "id": pid,
        "title": (card.get("title") or "").strip(),
        "price_iqd": price_min(card.get("price", "")),
        "price_raw": (card.get("price") or "").strip(),
        "price_usd": round(float(card.get("price_dollars") or 0), 2),
        "specs": " ".join((card.get("description") or "").split()),
        "code": card.get("code", ""),
        "id_cat": card.get("id_cat", ""),
        "url": f"https://alamani.iq/{model}/details/{pid}",
        "image": card.get("image", ""),
        "source_cat": f"{model}:{root_cat}",
    }


def fetch_category(model: str, cat_id: int, seen: dict, depth: int = 0) -> None:
    pad = "  " * depth
    try:
        data = post("list_view", {"model": model, "id_cat": cat_id, "id_cust": "0", "order": ""})
    except Exception as exc:                                  # noqa: BLE001
        print(f"{pad}! فشل قسم {model}:{cat_id} — {exc}", file=sys.stderr)
        return
    if not isinstance(data, dict):
        return

    cards = data.get("card") or []
    for c in cards:
        seen.setdefault(str(c.get("id")), normalize(c, model, cat_id))

    ids = [i for i in (data.get("id_material") or "").split(",") if i.strip()]
    print(f"{pad}» {model}:{cat_id} — {len(cards)} معروضة + {len(ids)} بالقائمة", file=sys.stderr)

    for start in range(0, len(ids), BATCH):
        chunk = ids[start:start + BATCH]
        time.sleep(DELAY)
        try:
            batch = post("list_view_materials", {
                "model": model, "id_cat": cat_id, "id_material": ",".join(chunk),
                "type_view": str(data.get("type_view") or 1), "order": "",
                "min": str(data.get("min") or 0), "max": str(data.get("max") or 99999999),
                "characteristic": "", "id_cust": "0",
            })
        except Exception as exc:                              # noqa: BLE001
            print(f"{pad}! فشل جلب دفعة — {exc}", file=sys.stderr)
            continue
        if isinstance(batch, dict):
            batch = batch.get("card") or []
        for c in batch or []:
            seen.setdefault(str(c.get("id")), normalize(c, model, cat_id))

    # الأقسام الفرعية (الماركات)
    subs = data.get("id_cat") or {}
    if depth == 0 and isinstance(subs, dict):
        for sub_id in subs:
            time.sleep(DELAY)
            fetch_category(model, int(sub_id), seen, depth + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cat", action="append", metavar="MODEL:ID",
                    help="قسم بصيغة computer:11 (يمكن تكراره)")
    ap.add_argument("--out", default="laptops.csv")
    args = ap.parse_args()

    cats = DEFAULT_CATS
    if args.cat:
        cats = []
        for spec in args.cat:
            model, _, cid = spec.partition(":")
            cats.append((model, int(cid)))

    seen: dict[str, dict] = {}
    for model, cid in cats:
        fetch_category(model, cid, seen)

    rows = sorted(seen.values(), key=lambda r: r["price_iqd"])
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                           ["id", "title", "price_iqd", "price_raw", "price_usd",
                            "specs", "code", "id_cat", "url", "image", "source_cat"])
        w.writeheader()
        w.writerows(rows)
    print(f"تم حفظ {len(rows)} منتج في {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
