#!/usr/bin/env python3
from pathlib import Path

ROOT=Path('/tmp/wfgg-radar')
T=ROOT/'src/game/remote-transport.js'
W=ROOT/'src/worker.js'
marker='WFGG_RADAR_MESSENGER_OUTBOX_WORKER_V624'

t=T.read_text(encoding='utf-8')
if marker not in t:
    anchor='  cartographerTick(token) { return this.request(\'/v1/cartographer/tick\', { body: { token } }); }\n'
    if t.count(anchor)!=1:
        raise SystemExit(f'V624_TRANSPORT_ANCHOR_COUNT={t.count(anchor)}')
    add='''  // WFGG_RADAR_MESSENGER_OUTBOX_WORKER_V624
  messengerOutboxCreate(draft) { return this.request('/v1/messenger/outbox/create', { body: draft }); }
  messengerOutboxQueue(id) { return this.request('/v1/messenger/outbox/queue?id=' + encodeURIComponent(id), { body: {} }); }
  messengerOutboxCancel(id) { return this.request('/v1/messenger/outbox/cancel?id=' + encodeURIComponent(id), { body: {} }); }
  messengerOutboxStatus(id) { return this.request('/v1/messenger/outbox/status?id=' + encodeURIComponent(id), { method: 'GET' }); }
  messengerOutboxList() { return this.request('/v1/messenger/outbox/list', { method: 'GET' }); }
'''
    t=t.replace(anchor,add+anchor,1)
T.write_text(t,encoding='utf-8')

w=W.read_text(encoding='utf-8')
if marker not in w:
    anchor="""      if (url.pathname === '/api/admin/users' && request.method === 'GET') {"""
    if w.count(anchor)!=1:
        raise SystemExit(f'V624_WORKER_ROUTE_ANCHOR_COUNT={w.count(anchor)}')
    block=r'''      // WFGG_RADAR_MESSENGER_OUTBOX_WORKER_V624
      if (url.pathname === '/api/radar/messenger/outbox' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const targetName = String(body.targetName || '').trim();
        const targetUid = String(body.targetUid || '').trim();
        const title = String(body.title || '');
        const contents = String(body.contents || '');
        const targetServer = Number(body.targetServer || 0) || 0;
        if (!targetName || !targetUid || !title || !contents) {
          throw Object.assign(new Error('MESSENGER_OUTBOX_DRAFT_REQUIRED_V624'), { status: 400 });
        }
        const draft = {
          targetName,
          targetUid,
          title,
          contents,
          sendLocalTime: Math.floor(Date.now() / 1000),
          senderServer: Number(session.serverId || 0) || 0,
          targetServer
        };
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY });
        try {
          const created = await transport.messengerOutboxCreate(draft);
          let queued = null;
          if (body.queue === true) {
            const id = String(created?.outbox?.record?.id || '').trim();
            if (!id) throw Object.assign(new Error('MESSENGER_OUTBOX_CREATE_ID_MISSING_V624'), { status: 502 });
            queued = await transport.messengerOutboxQueue(id);
          }
          return json({
            ok: true,
            version: 'V6.24',
            mode: 'DRY_RUN_ONLY',
            tokenUsed: false,
            lastwarMutation: false,
            networkSend: false,
            created,
            queued
          });
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/messenger/outbox/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const id = String(url.searchParams.get('id') || '').trim();
        if (!/^[a-f0-9]{24}$/.test(id)) throw Object.assign(new Error('MESSENGER_OUTBOX_ID_INVALID_V624'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY });
        try {
          const status = await transport.messengerOutboxStatus(id);
          return json({ ok: true, version: 'V6.24', mode: 'DRY_RUN_ONLY', tokenUsed: false, lastwarMutation: false, networkSend: false, status });
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    w=w.replace(anchor,block+anchor,1)
W.write_text(w,encoding='utf-8')
print('RADAR_V624_WORKER_OUTBOX=READY')
print('RADAR_V624_TOKEN_USED=NO')
print('RADAR_V624_LASTWAR_MUTATION=NO')
