// Service Worker für BIS PWA
const CACHE_NAME = 'bis-cache-v1';
const urlsToCache = [
  '/',
  '/static/style.css',
  '/static/script.js',
  '/static/manifest.json',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css'
];

// Installation
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Cache geöffnet');
        return cache.addAll(urlsToCache.filter(url => !url.startsWith('http')));
      })
      .catch(error => {
        console.log('Cache-Fehler:', error);
      })
  );
});

// Aktivierung
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Lösche alten Cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

// Fetch - Network First Strategie für dynamische Inhalte
self.addEventListener('fetch', event => {
  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Speichere erfolgreiche GET-Anfragen im Cache
        if (event.request.method === 'GET' && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Bei Netzwerkfehler versuche aus dem Cache zu laden
        return caches.match(event.request)
          .then(response => {
            if (response) {
              return response;
            }
            // Fallback für fehlende Seiten
            return caches.match('/');
          });
      })
  );
});

// Push-Benachrichtigungen empfangen
self.addEventListener('push', event => {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = { title: 'BIS Benachrichtigung', body: event.data.text() || 'Neue Benachrichtigung' };
    }
  } else {
    data = { title: 'BIS Benachrichtigung', body: 'Neue Benachrichtigung' };
  }
  
  const options = {
    body: data.body || data.nachricht || 'Neue Benachrichtigung',
    icon: data.icon || '/static/icons/icon-192.png',
    badge: data.badge || '/static/icons/icon-32.png',
    data: data.data || { url: '/dashboard' },
    tag: data.tag || 'bis-notification',
    requireInteraction: false
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'BIS Benachrichtigung', options)
  );
});

// Benachrichtigung anklicken
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  const url = event.notification.data?.url || '/dashboard';
  
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clientList => {
        // Prüfe ob bereits ein Fenster/Tab geöffnet ist
        for (let i = 0; i < clientList.length; i++) {
          const client = clientList[i];
          if (client.url === url && 'focus' in client) {
            return client.focus();
          }
        }
        // Öffne neues Fenster/Tab
        if (clients.openWindow) {
          return clients.openWindow(url);
        }
      })
  );
});

