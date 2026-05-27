const CACHE_NAME = "saveit-v1";
const STATIC = ["/", "/manifest.json"];

// تثبيت: كاش الملفات الأساسية
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE_NAME).then(c => c.addAll(STATIC))
  );
  self.skipWaiting();
});

// تفعيل: حذف الكاش القديم
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// جلب: Network First للـ API، Cache First للباقي
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // API دايماً من الشبكة
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(e.request));
    return;
  }

  // SSE دايماً من الشبكة
  if (url.pathname.startsWith("/api/progress/")) {
    e.respondWith(fetch(e.request));
    return;
  }

  // باقي الطلبات: جرب الشبكة أولاً، وإذا فشلت استخدم الكاش
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
