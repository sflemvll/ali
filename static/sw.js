// ════════════════════════════════════════════════════════════
// Kill-switch Service Worker
// يلغي أي service worker قديم، يمسح كل الكاش المخزّن،
// ويعيد تحميل الصفحة لتأخذ آخر نسخة — تلقائياً وبدون تدخل المستخدم.
// ════════════════════════════════════════════════════════════
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    // 1) امسح كل الكاش المخزّن (أي نسخة قديمة)
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));

    // 2) ألغِ تسجيل هذا الـ service worker نهائياً
    await self.registration.unregister();

    // 3) أعد تحميل كل التبويبات المفتوحة لتأخذ آخر نسخة من السيرفر
    const clients = await self.clients.matchAll({ type: "window" });
    for (const client of clients) {
      client.navigate(client.url);
    }
  })());
});
