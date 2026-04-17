// Aperture PWA service worker — minimal shell cache so the iPad can
// relaunch the UI even if the WiFi hiccups briefly. The /api/donate call
// itself always goes network-only; we never want to serve stale donation
// responses from cache.

const CACHE = "aperture-shell-v1";
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Network-only for API and bias-table — never serve stale.
  if (url.pathname.startsWith("/api/") || url.pathname === "/bias-table.json") {
    event.respondWith(fetch(event.request));
    return;
  }

  // Cache-first for shell assets.
  event.respondWith(
    caches.match(event.request).then((hit) => {
      if (hit) return hit;
      return fetch(event.request).then((resp) => {
        // Opportunistically cache successful GETs in the shell list.
        if (resp.ok && SHELL.includes(url.pathname)) {
          const clone = resp.clone();
          caches.open(CACHE).then((c) => c.put(event.request, clone));
        }
        return resp;
      }).catch(() => caches.match("/"));
    })
  );
});
