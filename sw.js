// ─────────────────────────────────────────────────────────────
//  VIZ FORECAST — Service Worker (modelled on Swim Manly's sw.js)
//  Strategy: network-first for the app shell, cache fallback offline.
//  The forecast itself is NOT cached here: the page keeps the last
//  forecast in localStorage and shows it with an "out of date" banner
//  when the Worker can't be reached. This file only makes sure the
//  page itself still opens with no signal.
//
//  Paths are RELATIVE so they resolve against /Forecast/, not the
//  domain root. Registered from index.html as './sw.js'.
//
//  Bump CACHE_VERSION when SHELL_ASSETS changes. Routine index.html
//  edits don't need it: the shell is fetched network-first.
// ─────────────────────────────────────────────────────────────

const CACHE_VERSION = '2026-09-19a';
const CACHE_NAME    = 'viz-forecast-' + CACHE_VERSION;

const SHELL_ASSETS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './image_1.png',
  './image_2.png',
  './icon-192.png',
  './marco2.png',
  // Must match the exact URL index.html requests, or it won't hit
  'https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap',
];

// API traffic is never cached: a stale score shown as current is the worst
// failure this app can have. The page handles offline data itself.
const PASSTHROUGH_HOSTS = [
  'bold-rain-6ded.sticasale.workers.dev',   // Worker: WillyWeather, Beachwatch, /log
  'api.open-meteo.com',
  'marine-api.open-meteo.com',
  'gkspukabnfbzrvjoewpc.supabase.co',
  'docs.google.com',                         // tuning Sheet CSV
  'script.google.com',                       // Sheet validation (admin)
  'fonts.gstatic.com',                       // font files: browser caches them itself
  'googletagmanager.com',
  'google-analytics.com',
  'hits.sh',
  'formspree.io',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(SHELL_ASSETS.map(url =>
        cache.add(url).catch(err => console.warn('[SW] pre-cache failed:', url, err))
      ))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys
        .filter(k => k.startsWith('viz-forecast-') && k !== CACHE_NAME)
        .map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return;
  if (req.method !== 'GET') return;
  if (PASSTHROUGH_HOSTS.some(h => url.hostname.includes(h))) return;
  // <video> asks for byte ranges; a plain cached 200 breaks Safari playback.
  // The splash plays once per device anyway, so just let it stream.
  if (/\.mp4$/i.test(url.pathname) || req.headers.has('range')) return;

  event.respondWith(
    fetch(req)
      .then(res => {
        if (res && res.status === 200 && (res.type === 'basic' || res.type === 'cors')) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(c => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then(hit => {
        if (hit) return hit;
        if (req.mode === 'navigate') return caches.match('./index.html');
        return new Response('Offline', { status: 503, statusText: 'Service Unavailable' });
      }))
  );
});
