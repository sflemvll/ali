#!/usr/bin/env python3
"""فلترة وترتيب ملف laptops.csv حسب صلاحيته لشغل البرمجة.

- يحصر النتائج ضمن مدى سعري (افتراضيًا 500,000 - 800,000 دينار)
- يستبعد Celeron / Pentium / Atom ورام 4 جيجا وشاشات 1366×768 وأقراص HDD
- يرتّب الباقي بنقاط: الرام، التخزين، جيل المعالج، جودة البناء، الشاشة

الاستعمال:
    python3 tools/alamani_filter.py laptops.csv
    python3 tools/alamani_filter.py laptops.csv --min 300000 --max 900000
    python3 tools/alamani_filter.py laptops.csv --out shortlist.csv --show-rejected
"""
from __future__ import annotations

import argparse
import csv
import re

BAD_CPU = re.compile(r"\b(celeron|pentium|atom|mediatek|athlon\s*3050u|core\s*m3)\b", re.I)
BAD_SCREEN = re.compile(r"1366\s*[x*×]\s*768", re.I)
HDD_ONLY = re.compile(r"\bHDD\b", re.I)

# ماركات فئة الأعمال: كيبورد أفضل، بناء أمتن، قطع غيار متوفرة
BUSINESS = re.compile(r"\b(thinkpad|latitude|elitebook|probook|thinkbook|expertbook|zbook|precision)\b", re.I)
GAMING = re.compile(r"\b(gaming|victus|nitro|predator|legion|tuf|rog|cyborg|loq|omen|gf63)\b", re.I)
NOT_LAPTOP = re.compile(r"\b(adapter|charger|charging|battery|bag|mouse|keyboard only)\b", re.I)


def ram_gb(text: str) -> int:
    """أكبر قيمة رام مذكورة (بعض العناوين تكتب 8GB/16GB للخيارين)."""
    out = []
    for m in re.finditer(r"(\d{1,3})\s*GB", text, re.I):
        tail = text[m.end():m.end() + 12].upper()
        if "SSD" in tail or "EMMC" in tail or "NVME" in tail:
            continue                      # هذي سعة تخزين وليست رام
        v = int(m.group(1))
        if v in (4, 6, 8, 12, 16, 24, 32, 64):
            out.append(v)
    return max(out) if out else 0


def ssd_gb(text: str) -> int:
    best = 0
    for m in re.finditer(r"(\d{3,4})\s*GB\s*(?:SSD|NVME|EMMC)", text, re.I):
        best = max(best, int(m.group(1)))
    for _ in re.finditer(r"(\d)\s*TB\s*SSD", text, re.I):
        best = max(best, 1024)
    return best


def cpu_info(text: str) -> tuple[str, int, int]:
    """يرجع (اسم المعالج، الفئة 3/5/7/9، الجيل)."""
    m = re.search(r"(?:CORE\s*)?[iI]([3579])[- ]?(\d{4,5})([A-Z]{0,2})", text)
    if m:
        tier, num = int(m.group(1)), m.group(2)
        gen = int(num[:2]) if len(num) == 5 else int(num[0])
        return f"i{tier}-{num}{m.group(3)}", tier, gen
    m = re.search(r"ULTRA\s*([579])[- ]?(\d{3})", text, re.I)
    if m:
        return f"Ultra {m.group(1)}-{m.group(2)}", int(m.group(1)), 14
    m = re.search(r"RYZEN\s*([3579])[- ]?(\d{4})", text, re.I)
    if m:
        return f"Ryzen {m.group(1)}-{m.group(2)}", int(m.group(1)), int(m.group(2)[0])
    m = re.search(r"\bM([1234])\b", text)
    if m:
        return f"Apple M{m.group(1)}", 7, 12 + int(m.group(1))
    m = re.search(r"CORE\s*([3579])[- ]?(\d{3})", text, re.I)
    if m:
        return f"Core {m.group(1)}-{m.group(2)}", int(m.group(1)), 13
    m = re.search(r"[iI]([3579])[- ]?N(\d{3})", text)   # N-series منخفض الطاقة
    if m:
        return f"i{m.group(1)}-N{m.group(2)} (فئة موفّرة)", 3, 12
    m = re.search(r"CORE\s*[iI]([3579])(?![-\s]*[A-Za-z]?\d{3})", text)   # "CORE i7 6-CORE"
    if m:
        return f"Core i{m.group(1)} (جيل قديم)", int(m.group(1)), 0
    return "?", 0, 0


def score(row: dict) -> tuple[int, list[str]]:
    text = f"{row['title']} {row['specs']}"
    pts, why = 0, []

    r = ram_gb(text)
    if r >= 16:
        pts += 40; why.append(f"رام {r} جيجا")
    elif r >= 8:
        pts += 22; why.append(f"رام {r} جيجا")
    elif r:
        pts += 2; why.append(f"رام {r} جيجا فقط")

    s = ssd_gb(text)
    if s >= 512:
        pts += 22; why.append(f"تخزين {s} SSD")
    elif s >= 256:
        pts += 14; why.append(f"تخزين {s} SSD")
    elif s:
        pts += 4; why.append(f"تخزين {s} فقط")

    name, tier, gen = cpu_info(text)
    pts += {9: 20, 7: 18, 5: 16, 3: 8}.get(tier, 0)
    pts += min(gen, 14)
    if name != "?":
        why.append(f"معالج {name}")

    if BUSINESS.search(text):
        pts += 15; why.append("فئة أعمال (كيبورد وبناء أمتن)")
    if GAMING.search(text):
        pts -= 8; why.append("قيمنك: حرارة ووزن وبطارية أقل")
    if re.search(r"\bFHD\b|1920\s*[x*×]\s*1080|1080\s*[x*×]\s*1920", text, re.I):
        pts += 6
    if re.search(r"\bIPS\b", text, re.I):
        pts += 4; why.append("شاشة IPS")
    if re.search(r"مستخدم|USED", text, re.I):
        why.append("مستعمل")
    return pts, why


def reject_reason(row: dict) -> str | None:
    text = f"{row['title']} {row['specs']}"
    if NOT_LAPTOP.search(row["title"]):
        return "ليس لابتوب"
    if BAD_CPU.search(text):
        return "معالج ضعيف (Celeron/Pentium/Athlon)"
    if BAD_SCREEN.search(text):
        return "شاشة 1366×768"
    if HDD_ONLY.search(text) and not re.search(r"SSD", text, re.I):
        return "قرص HDD بلا SSD"
    if ram_gb(text) and ram_gb(text) < 8:
        return f"رام {ram_gb(text)} جيجا"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file", nargs="?", default="laptops.csv")
    ap.add_argument("--min", type=int, default=500_000)
    ap.add_argument("--max", type=int, default=800_000)
    ap.add_argument("--out", default="shortlist.csv")
    ap.add_argument("--show-rejected", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv_file, encoding="utf-8-sig")))
    kept, rejected = [], []
    for row in rows:
        price = int(row["price_iqd"] or 0)
        if not (args.min <= price <= args.max):
            continue
        reason = reject_reason(row)
        if reason:
            rejected.append((row, reason))
            continue
        pts, why = score(row)
        row["score"] = pts
        row["why"] = " · ".join(why)
        kept.append(row)

    kept.sort(key=lambda r: (-r["score"], int(r["price_iqd"])))

    print(f"\nضمن {args.min:,} - {args.max:,} دينار: {len(kept)} جهاز مناسب "
          f"({len(rejected)} مستبعد)\n")
    for i, r in enumerate(kept, 1):
        print(f"{i}. [{r['score']:>3}] {int(r['price_iqd']):>9,} د.ع  {r['title'][:70]}")
        print(f"     {r['why']}")
        print(f"     {r['url']}")
    if args.show_rejected and rejected:
        print("\nالمستبعدون:")
        for r, reason in sorted(rejected, key=lambda x: int(x[0]["price_iqd"])):
            print(f"  - {int(r['price_iqd']):>9,} د.ع  {r['title'][:60]} → {reason}")

    if kept:
        cols = ["score", "price_iqd", "title", "why", "specs", "url"]
        with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(kept)
        print(f"\nحُفظت القائمة المختصرة في {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
