// This app has no service worker. Browsers that visited another project on the same
// address (for example localhost:3000) keep that project's old service worker, which can
// serve stale files here. This one replaces it, clears its caches and removes itself.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.registration.unregister();
  })());
});
