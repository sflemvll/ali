# أدوات سحب منتجات alamani.iq

سكربتات لسحب قوائم المنتجات من موقع الأماني وفلترتها لاختيار لابتوب للبرمجة.

## كيف يعمل السحب

الموقع تطبيق Nuxt يجلب بياناته من واجهة JSON، فبدل تشغيل متصفح
نستدعي نفس الواجهتين اللتين يستدعيهما الموقع:

| الطلب | المعطيات | المُرجَع |
|---|---|---|
| `POST /api_app/list_view` | `model, id_cat, id_cust, order` | `card[]` (أول دفعة)، `id_cat{}` (الأقسام الفرعية)، `id_material` (بقية المعرفات) |
| `POST /api_app/list_view_materials` | `model, id_cat, id_material, type_view, order, min, max, characteristic, id_cust` | مصفوفة المنتجات لتلك المعرفات |

القاعدة: `https://apiapp.alamani.iq/api_app/`

### أرقام الأقسام المفيدة

| الرابط | القسم |
|---|---|
| `computer:11` | لابتوبات مستخدمة |
| `computer:7` | لابتوب Laptop (جديد) |
| `computer:9` | تجميعات مستخدمة |
| `computer:3` | قطع الحاسوب |
| `computer:88` | شاشات |

قائمة الأقسام كاملة من: `https://apig.alamani.iq/menu`

## الاستعمال

```bash
# 1) السحب (لابتوبات مستعملة + جديدة، مع الأقسام الفرعية)
python3 tools/alamani_scrape.py --out laptops.csv

# قسم واحد فقط
python3 tools/alamani_scrape.py --cat computer:11 --out used.csv

# 2) الفلترة والترتيب لشغل البرمجة
python3 tools/alamani_filter.py laptops.csv                       # 500ألف - 800ألف
python3 tools/alamani_filter.py laptops.csv --min 250000 --max 800000 --show-rejected
```

`alamani_scrape.py` يعتمد على المكتبة القياسية فقط، وبينه وبين كل طلب ثانية تأخير.

### بديل المتصفح

`alamani_scrape_playwright.py` يفتح الصفحة بمتصفح حقيقي ويسكرول للأسفل،
ويلتقط المنتجات من ردود JSON نفسها. استعمله فقط إذا تغيّرت الواجهة أو صار
الوصول المباشر محجوبًا:

```bash
pip install playwright && playwright install chromium
python3 tools/alamani_scrape_playwright.py --url https://alamani.iq/computer/list_view/11
```

## معايير الفلترة

يُستبعد: Celeron / Pentium / Atom / Athlon 3050U، رام 4 جيجا، شاشة 1366×768،
قرص HDD بلا SSD، والملحقات (شواحن وغيرها).

الترتيب بنقاط: رام 16 جيجا (40) > 8 (22) — تخزين 512 SSD (22) > 256 (14) —
فئة المعالج وجيله — إضافة 15 لأجهزة فئة الأعمال (ThinkPad / Latitude /
EliteBook / ProBook) وخصم 8 لأجهزة القيمنك (حرارة ووزن وبطارية أقل).

## `data/`

لقطة من النتائج بتاريخ 2026-08-22: `laptops.csv` (92 منتجًا) و
`shortlist.csv` (المرشحون ضمن 500-800 ألف). الأسعار تتغيّر — أعد تشغيل
السحب قبل الاعتماد عليها.
