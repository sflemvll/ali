const CACHE_NAME = "saveit-v2";
const STATIC = ["/manifest.json"];

// تثبيت: كاش الملفات الأساسية فقط (بدون الصفحة الرئيسية)
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(c => c.addAll(STATIC))
  );
  self.skipWaiting();
});

// تفعيل: احذف كل الكاش القديم (v1 وغيره)
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// جلب
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // API و SSE: دايماً من الشبكة
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(e.request));
    return;
  }

  // صفحات HTML (التنقّل): دايماً من الشبكة — تضمن آخر نسخة بدون تخزين
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request));
    return;
  }

  // باقي الملفات الثابتة: جرّب الشبكة أولاً، وإذا فشلت استخدم الكاش
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
