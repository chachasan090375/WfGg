/* WFGG_TRAIN_PUSH_SW_V1 */
'use strict';

self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (_) {
    try { data = { body: event.data ? event.data.text() : '' }; } catch (_) {}
  }
  const title = data.title || 'WfGg Train';
  const options = {
    body: data.body || '',
    icon: '/train/assets/icon-192.png',
    tag: data.tag || 'wfgg-train-reminder',
    renotify: true,
    data: { url: data.url || '/train/', ...(data.data || {}) }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = event.notification?.data?.url || '/train/';
  event.waitUntil((async () => {
    const windows = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      try {
        const u = new URL(client.url);
        if (u.origin === self.location.origin && u.pathname.startsWith('/train/')) {
          if ('focus' in client) {
            await client.focus();
            if ('navigate' in client && client.url !== new URL(target, self.location.origin).href) {
              await client.navigate(target);
            }
            return;
          }
        }
      } catch (_) {}
    }
    if (clients.openWindow) await clients.openWindow(target);
  })());
});
