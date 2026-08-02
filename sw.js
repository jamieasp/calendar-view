const CACHE_NAME = 'calendar-view-v2-clawjcal';
const ASSETS = [
  '/calendar-view/',
  '/calendar-view/index.html',
  '/calendar-view/manifest.webmanifest',
  '/calendar-view/health-data.json',
  '/calendar-view/icon-192.png',
  '/calendar-view/icon-512.png',
  '/calendar-view/maskable-512.png',
  '/calendar-view/apple-touch-icon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
