#!/usr/bin/env python3
from pathlib import Path

TRANSPORT = Path('/tmp/wfgg-radar/src/game/remote-transport.js')
WORKER = Path('/tmp/wfgg-radar/src/worker.js')

transport = TRANSPORT.read_text(encoding='utf-8')
if 'WFGG_RADAR_SEED_SCOUT_TRANSPORT_V6193' not in transport:
    anchor = "  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }\n"
    if transport.count(anchor) != 1:
        raise SystemExit(f'V6193_TRANSPORT_ANCHOR_COUNT={transport.count(anchor)}')
    addition = anchor + """  // WFGG_RADAR_SEED_SCOUT_TRANSPORT_V6193
  startSeedScout(token, { limit = 8, region = 4, minTargetPlayers = 20 } = {}) {
    return this.request('/v1/collector/server-seed-scout/start', {
      body: { token, limit, region, minTargetPlayers }
    });
  }
  seedScoutStatus(id) {
    return this.request(`/v1/collector/server-seed-scout/status?id=${encodeURIComponent(id)}`, { method: 'GET' });
  }
"""
    TRANSPORT.write_text(transport.replace(anchor, addition, 1), encoding='utf-8')
    print('RADAR_V6193_SEED_SCOUT_TRANSPORT=PATCHED')
else:
    print('RADAR_V6193_SEED_SCOUT_TRANSPORT=ALREADY_PRESENT')

worker = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_SEED_SCOUT_WORKER_V6193' not in worker:
    anchor = "      if (url.pathname === '/api/radar/search/start' && request.method === 'POST') {\n"
    if worker.count(anchor) != 1:
        raise SystemExit(f'V6193_WORKER_ANCHOR_COUNT={worker.count(anchor)}')
    block = r'''      // WFGG_RADAR_SEED_SCOUT_WORKER_V6193
      if (url.pathname === '/api/radar/seed-scout/start' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const limit = body.limit == null ? 8 : Number(body.limit);
        const region = body.region == null ? 4 : Number(body.region);
        const minTargetPlayers = body.minTargetPlayers == null ? 20 : Number(body.minTargetPlayers);
        if (!Number.isInteger(limit) || limit < 1 || limit > 20) throw Object.assign(new Error('SEED_SCOUT_LIMIT_INVALID'), { status: 400 });
        if (!Number.isInteger(region) || region < 0 || region > 8) throw Object.assign(new Error('SEED_SCOUT_REGION_INVALID'), { status: 400 });
        if (!Number.isInteger(minTargetPlayers) || minTargetPlayers < 1 || minTargetPlayers > 500) throw Object.assign(new Error('SEED_SCOUT_MIN_PLAYERS_INVALID'), { status: 400 });

        const record = await getCredential(env, session.gameUid);
        if (!record) throw Object.assign(new Error('GAME_CREDENTIAL_NOT_FOUND'), { status: 409 });
        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
        const token = await decryptGameToken(
          { ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version },
          vaultKey,
          session.gameUid
        );
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          const started = await transport.startSeedScout(token, { limit, region, minTargetPlayers });
          const job = started?.job || null;
          if (!job?.id) throw Object.assign(new Error('SEED_SCOUT_JOB_START_INVALID'), { status: 502 });
          return json({ ok: true, readonly: true, collectorMutation: false, job }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/seed-scout/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const id = String(url.searchParams.get('id') || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('SEED_SCOUT_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          const status = await transport.seedScoutStatus(id);
          const job = status?.job || null;
          if (!job) throw Object.assign(new Error('SEED_SCOUT_JOB_STATUS_INVALID'), { status: 502 });
          return json({ ok: true, readonly: true, collectorMutation: false, job });
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    WORKER.write_text(worker.replace(anchor, block + anchor, 1), encoding='utf-8')
    print('RADAR_V6193_SEED_SCOUT_WORKER=PATCHED')
else:
    print('RADAR_V6193_SEED_SCOUT_WORKER=ALREADY_PRESENT')

print('RADAR_V6193_SEED_SCOUT_WORKER=READY')
