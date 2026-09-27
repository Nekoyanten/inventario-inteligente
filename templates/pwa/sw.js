const CACHE = "{{ version }}";
const ESTATICOS = ["{{ css }}", "{{ js }}", "{{ icono }}", "/sin-conexion/"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ESTATICOS))); self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(req).then((r) => r || fetch(req).then((resp) => {
      const copia = resp.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); return resp;
    })));
    return;
  }
  // Páginas: red primero; si no hay conexión, la última versión guardada (consultar stock fuera del negocio)
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("application/json")) {
    e.respondWith(fetch(req).then((resp) => {
      if (resp.ok && !url.pathname.startsWith("/admin")) { const copia = resp.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); }
      return resp;
    }).catch(() => caches.match(req).then((r) => r || caches.match("/sin-conexion/"))));
  }
});
