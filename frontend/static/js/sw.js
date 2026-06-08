const SHELL = [
  "/",
  "/static/css/style.css",
  "/static/js/app.js",
  "/static/js/api.js",
  "/static/js/favorites.js",
  "/static/js/chart.umd.min.js",
  "/static/img/favicon.svg",
];

// Fetches the content-hash version from the API (changes on every deploy).
// Falls back to a timestamp-based name if offline or server unavailable.
async function resolveCache() {
  try {
    const r = await fetch("/version", { cache: "no-store" });
    if (r.ok) {
      const { version } = await r.json();
      return `ticoprice-${version}`;
    }
  } catch {}
  return `ticoprice-fallback-${Date.now()}`;
}

self.addEventListener("install", (e) => {
  e.waitUntil(
    resolveCache()
      .then((name) => caches.open(name).then((c) => c.addAll(SHELL)))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    resolveCache().then((current) =>
      caches.keys()
        .then((keys) => Promise.all(
          keys
            .filter((k) => k.startsWith("ticoprice-") && k !== current)
            .map((k) => caches.delete(k))
        ))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const { request } = e;
  const url = new URL(request.url);

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
          caches.open(`ticoprice-api`).then((c) => c.put(request, clone));
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
          resolveCache().then((name) => caches.open(name).then((c) => c.put(request, clone)));
          return res;
        });
      })
    );
    return;
  }

  // SPA shell: network-first, fallback to cached "/"
  e.respondWith(
    fetch(request)
      .then((res) => {
        const clone = res.clone();
        resolveCache().then((name) => caches.open(name).then((c) => c.put(request, clone)));
        return res;
      })
      .catch(() => caches.match(request) || caches.match("/"))
  );
});
