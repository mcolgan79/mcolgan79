/* OptPoP service worker — cache-first for the app shell so the PWA works offline. */
const CACHE = 'optpop-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(['./', './index.html'])),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return
  event.respondWith(
    caches.match(event.request).then(
      (hit) =>
        hit ||
        fetch(event.request).then((res) => {
          const copy = res.clone()
          if (res.ok && new URL(event.request.url).origin === location.origin) {
            caches.open(CACHE).then((cache) => cache.put(event.request, copy))
          }
          return res
        }),
    ),
  )
})
