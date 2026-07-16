/* OptPoP service worker.
   - Navigations: network-first so a new deploy is picked up immediately,
     falling back to cache offline.
   - Same-origin assets (hashed filenames): cache-first.
   - Cross-origin requests (Tradier API): never intercepted. */
const CACHE = 'optpop-v2'

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(['./', './index.html'])))
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
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== location.origin) return
  // Never cache API calls (Stripe subscription status must always be live).
  if (url.pathname.startsWith('/api/')) return

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone()
          if (res.ok) caches.open(CACHE).then((cache) => cache.put(req, copy))
          return res
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match('./index.html'))),
    )
    return
  }

  event.respondWith(
    caches.match(req).then(
      (hit) =>
        hit ||
        fetch(req).then((res) => {
          const copy = res.clone()
          if (res.ok) caches.open(CACHE).then((cache) => cache.put(req, copy))
          return res
        }),
    ),
  )
})
