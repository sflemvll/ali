# 🚀 كيف ترفع الموقع على Google Cloud Run

## الخطوات بالترتيب:

### 1️⃣ ثبّت Google Cloud CLI
اذهب لهذا الرابط وحمّل الأداة:
https://cloud.google.com/sdk/docs/install

### 2️⃣ سجّل دخول
```bash
gcloud auth login
```

### 3️⃣ أنشئ مشروع جديد
```bash
gcloud projects create yt-downloader-app --name="YT Downloader"
gcloud config set project yt-downloader-app
```

### 4️⃣ فعّل الخدمات المطلوبة
```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

### 5️⃣ ارفع وانشر بأمر واحد (من داخل مجلد المشروع)
```bash
gcloud run deploy yt-downloader \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 300
```

### ✅ النتيجة
ستحصل على رابط مثل:
https://yt-downloader-xxxx-uc.a.run.app

هذا رابط موقعك — يشتغل من أي مكان في العالم 24/7 🌍

---

## 💡 ملاحظات مهمة:
- الطبقة المجانية = 2 مليون طلب شهرياً مجاناً
- تحتاج بطاقة بنكية للتسجيل (لن يُشحن منها شيء في الطبقة المجانية)
- لإضافة الإعلانات مستقبلاً: أزل التعليق عن أسطر <!-- ad-slot --> في index.html

## 🔄 تحديث الموقع لاحقاً:
```bash
gcloud run deploy yt-downloader --source .
```
