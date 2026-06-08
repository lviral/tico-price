const CACHE = "ticoprice-v1";
const SHELL = [
  "/",
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/js/api.js",
  "/static/js/favorites.js",
  "/static/img/favicon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  const url = new URL(request.url);

  // Skip non-GET and cross-origin (except CDN for Chart.js)
  if (request.method !== "GET") return;

  // API routes: network-first, cache fallback
  if (url.pathname.startsWith("/products") ||
      url.pathname.startsWith("/trending") ||
      url.pathname.startsWith("/categories") ||
      url.pathname.startsWith("/stores") ||
      url.pathname.startsWith("/deals") ||
      url.pathname.startsWith("/inflation")) {
    e.respondWith(
      fetch(request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(request, clone));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(request, clone));
          return res;
        });
      })
    );
    return;
  }

  // SPA shell (HTML pages): network-first, fallback to cached "/"
  e.respondWith(
    fetch(request)
      .then((res) => {
        const clone = res.clone();
        caches.open(CACHE).then((c) => c.put(request, clone));
        return res;
      })
      .catch(() => caches.match(request) || caches.match("/"))
  );
});
