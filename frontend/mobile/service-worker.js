/*
 * AvertAI mobile app service worker.
 *
 * Strategy:
 *  - App shell (this HTML file, manifest, icon): cache-first, so the app
 *    still opens with zero connectivity — matches the blueprint's "offline
 *    and accessibility suite" requirement.
 *  - GET requests to the backend API (predictions, resources, etc.):
 *    stale-while-revalidate — show the last cached response instantly, then
 *    refresh it in the background for next time. This stands in for the
 *    blueprint's "predictions stored locally for 7 days" spec; a production
 *    build would additionally prune entries older than 7 days from an
 *    IndexedDB store with actual timestamps rather than relying on the
 *    Cache API's insertion order.
 *  - POST/PUT/DELETE (report submissions, SOS, verify actions): always
 *    network — mutations are never served from cache. If offline, the page's
 *    own JS already shows a "queued for sync" message; a production build
 *    would add a Background Sync registration here to actually replay the
 *    queued request once connectivity returns.
 */

const SHELL_CACHE = "avertai-shell-v1";
const API_CACHE = "avertai-api-v1";
const SHELL_ASSETS = ["./index.html", "./manifest.json", "./icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== API_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Never touch non-GET requests — submissions/SOS/verify must always hit
  // the network live, or fail visibly so the page can show its own
  // "queued for sync" UI rather than a silently stale cached response.
  if (req.method !== "GET") return;

  const isApiCall = url.pathname.startsWith("/api/v1/");
  const isShellAsset = SHELL_ASSETS.some((a) => req.url.endsWith(a.replace("./", "")));

  const isMapTile = url.href.includes("tile.openstreetmap.org") || url.href.includes("mt1.google.com");

  if (isShellAsset || isMapTile) {
    event.respondWith(
      caches.match(req).then((cached) => {
          if (cached) return cached;
          return fetch(req).then(res => {
              if (res.ok && isMapTile) {
                  const clonedRes = res.clone();
                  caches.open(SHELL_CACHE).then(cache => cache.put(req, clonedRes));
              }
              return res;
          });
      })
    );
    return;
  }

  if (isApiCall) {
    event.respondWith(
      caches.open(API_CACHE).then(async (cache) => {
        const cached = await cache.match(req);
        const networkFetch = fetch(req)
          .then((res) => {
            if (res.ok) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || networkFetch;
      })
    );
  }
});
