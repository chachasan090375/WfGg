#!/usr/bin/env python3
from pathlib import Path

TRANSPORT = Path('/tmp/wfgg-radar/src/game/remote-transport.js')
WORKER = Path('/tmp/wfgg-radar/src/worker.js')

transport = TRANSPORT.read_text(encoding='utf-8')
if 'WFGG_RADAR_AUTOPILOT_TRANSPORT_V6194' not in transport:
    anchor = """  seedScoutStatus(id) {
    return this.request(`/v1/collector/server-seed-scout/status?id=${encodeURIComponent(id)}`, { method: 'GET' });
  }
"""
    if transport.count(anchor) != 1:
        raise SystemExit(f'V6194_TRANSPORT_ANCHOR_COUNT={transport.count(anchor)}')
    addition = anchor + """  // WFGG_RADAR_AUTOPILOT_TRANSPORT_V6194
  startAutopilot(token, options = {}) {
    return this.request('/v1/collector/autopilot/start', {
      body: { token, ...options }
    });
  }
  autopilotStatus(id) {
    return this.request(`/v1/collector/autopilot/status?id=${encodeURIComponent(id)}`, { method: 'GET' });
  }
  stopAutopilot(id) {
    return this.request('/v1/collector/autopilot/stop', {
      body: { id }
    });
  }
"""
    TRANSPORT.write_text(transport.replace(anchor, addition, 1), encoding='utf-8')
    print('RADAR_V6194_AUTOPILOT_TRANSPORT=PATCHED')
else:
    print('RADAR_V6194_AUTOPILOT_TRANSPORT=ALREADY_PRESENT')

worker = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_AUTOPILOT_WORKER_V6194' not in worker:
    anchor = "      // WFGG_RADAR_SEED_SCOUT_WORKER_V6193\n"
    if worker.count(anchor) != 1:
        raise SystemExit(f'V6194_WORKER_ANCHOR_COUNT={worker.count(anchor)}')
    block = r'''      // WFGG_RADAR_AUTOPILOT_WORKER_V6194
      if (url.pathname === '/api/radar/autopilot/start' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const initialSeed = String(body.initialSeed || '').trim();
        const fullCyclesPerCluster = body.fullCyclesPerCluster == null ? 3 : Number(body.fullCyclesPerCluster);
        const maxClusters = body.maxClusters == null ? 5 : Number(body.maxClusters);
        if (!Number.isInteger(fullCyclesPerCluster) || fullCyclesPerCluster < 1 || fullCyclesPerCluster > 5) {
          throw Object.assign(new Error('AUTOPILOT_FULL_CYCLES_INVALID'), { status: 400 });
        }
        if (!Number.isInteger(maxClusters) || maxClusters < 1 || maxClusters > 20) {
          throw Object.assign(new Error('AUTOPILOT_MAX_CLUSTERS_INVALID'), { status: 400 });
        }

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
          const started = await transport.startAutopilot(token, {
            initialSeed,
            fullCyclesPerCluster,
            maxClusters,
            partialRetryLimit: 5,
            consecutiveFailureLimit: 3,
            scoutLimit: 8,
            scoutMaxBatches: 20,
            scoutRegion: 4,
            scoutMinPlayers: 20
          });
          const job = started?.job || null;
          if (!job?.id) throw Object.assign(new Error('AUTOPILOT_JOB_START_INVALID'), { status: 502 });
          return json({
            ok: true,
            gameReadonly: true,
            gameMutation: false,
            collectorMutation: true,
            browserRequired: false,
            job
          }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/autopilot/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const id = String(url.searchParams.get('id') || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('AUTOPILOT_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          return json(await transport.autopilotStatus(id));
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/autopilot/stop' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const id = String(body.id || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('AUTOPILOT_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          return json(await transport.stopAutopilot(id), 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    WORKER.write_text(worker.replace(anchor, block + anchor, 1), encoding='utf-8')
    print('RADAR_V6194_AUTOPILOT_WORKER=PATCHED')
else:
    print('RADAR_V6194_AUTOPILOT_WORKER=ALREADY_PRESENT')

print('RADAR_V6194_AUTOPILOT_WORKER=READY')
