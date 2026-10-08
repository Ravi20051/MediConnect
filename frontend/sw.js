/**
 * MediConnect — Service Worker (Application Shell Offline Caching)
 * Provides offline application shell loading for ASHA Field Companion.
 * 
 * Rules:
 * 1. Only caches frontend application shell / static assets (HTML, CSS, JS, manifest).
 * 2. NEVER caches or fakes clinical API responses (/api/*).
 * 3. Does NOT fabricate predictions, clinical stats, or patient records.
 * 4. Enables the user to open/refresh the application shell while disconnected.
 */

const CACHE_NAME = 'mediconnect-shell-v2.1';

const APP_SHELL_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/static/css/styles.css?v=2.1.0',
  '/static/js/i18n.js?v=2.1.0',
  '/static/js/app.js?v=2.1.0',
  '/static/css/styles.css',
  '/static/js/i18n.js',
  '/static/js/app.js'
];

// 1. Installation: Pre-cache application shell assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[SW] Pre-caching MediConnect application shell assets');
      return cache.addAll(APP_SHELL_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

// 2. Activation: Clean up any old cache versions
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Purging outdated cache:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// 3. Fetch interception:
// Serve cached shell for navigation/static assets when offline.
// ALWAYS pass /api/* requests straight to network without fake responses.
self.addEventListener('fetch', event => {
  const req = event.request;
  const url = new URL(req.url);

  // STRICT RULE: NEVER intercept or cache dynamic backend API requests
  if (url.pathname.startsWith('/api/')) {
    return; // Standard network fetch, fails naturally if offline
  }

  // Non-GET requests (POST sync push, etc.) must not be cached by SW
  if (req.method !== 'GET') {
    return;
  }

  // Navigation requests (refreshing page or loading root while offline)
  if (req.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html') {
    event.respondWith(
      fetch(req).then(networkResponse => {
        if (networkResponse && networkResponse.status === 200) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
        }
        return networkResponse;
      }).catch(async () => {
        // Network unavailable -> return cached application shell
        console.log('[SW] Network unreachable. Serving cached application shell for navigation.');
        const cached = await caches.match('/index.html') || await caches.match('/');
        return cached;
      })
    );
    return;
  }

  // Static assets (CSS, JS, manifest)
  event.respondWith(
    caches.match(req).then(cachedResponse => {
      if (cachedResponse) {
        // Return cached asset immediately, revalidate in background if online
        fetch(req).then(networkResponse => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then(cache => cache.put(req, networkResponse));
          }
        }).catch(() => {
          // Silent catch when offline
        });
        return cachedResponse;
      }

      // If not in cache, try network and cache for next time if static asset
      return fetch(req).then(networkResponse => {
        if (networkResponse && networkResponse.status === 200 && (
          url.pathname.includes('/static/') ||
          url.pathname.endsWith('.css') ||
          url.pathname.endsWith('.js') ||
          url.pathname.endsWith('.json')
        )) {
          const clone = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, clone));
        }
        return networkResponse;
      });
    })
  );
});
