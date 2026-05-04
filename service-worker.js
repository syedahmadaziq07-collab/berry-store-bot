// Berry Store Admin – Service Worker (PWA + Push Notifications)
const CACHE_NAME = 'berry-store-v1';
const ASSETS = [
  './dashboard.html',
  './manifest.json',
  'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2',
  'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js'
];

// ====== INSTALL ======
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE_NAME)
      .then(c => c.addAll(ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ====== ACTIVATE ======
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ====== FETCH (network-first, cache fallback) ======
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(r => {
        const clone = r.clone();
        caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        return r;
      })
      .catch(() => caches.match(e.request))
  );
});

// ====== PUSH ======
self.addEventListener('push', e => {
  let data = { title: 'Berry Store', body: 'New notification', tag: 'general' };
  try { data = e.data.json(); } catch (_) {}
  const opts = {
    body: data.body || '',
    icon: './icons/icon-192.png',
    badge: './icons/icon-192.png',
    tag: data.tag || 'berry-' + Date.now(),
    data: { url: data.url || './dashboard.html' },
    vibrate: [200, 100, 200],
    requireInteraction: data.requireInteraction || false
  };
  e.waitUntil(self.registration.showNotification(data.title || 'Berry Store', opts));
});

// ====== NOTIFICATION CLICK ======
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || './dashboard.html';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(wl => {
      for (const w of wl) {
        if (w.url.includes('dashboard') && 'focus' in w) return w.focus();
      }
      return clients.openWindow(url);
    })
  );
});
