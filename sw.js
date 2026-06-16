// Service worker mínimo y "siempre online".
//
// No cachea datos: la app carga siempre la versión EN VIVO de la web, así que un
// cambio en index.html se ve al instante tanto en el navegador como en la app
// Android (TWA) que envuelve esta misma web. Su única razón de existir es que la
// PWA sea instalable y empaquetable para Google Play.

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
  // Passthrough a la red. Sin caché => contenido siempre actualizado.
  event.respondWith(fetch(event.request));
});
