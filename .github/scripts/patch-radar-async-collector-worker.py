#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess
import sys

p = Path('/tmp/wfgg-radar/src/worker.js')
s = p.read_text()
marker = "      if (url.pathname === '/api/radar/search' && request.method === 'GET') {"

if "'/api/radar/search/start'" in s:
    print('RADAR_ASYNC_COLLECTOR_PATCH=ALREADY_PRESENT')
else:
    if marker not in s:
        raise SystemExit('RADAR_ASYNC_COLLECTOR_PATCH_ANCHOR_MISSING')
    block = r'''      if (url.pathname === '/api/radar/search/start' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const query = String(body.q || body.query || '').trim();
        if (!query || query.length > 128) throw Object.assign(new Error('RADAR_QUERY_REQUIRED'), { status: 400 });
        const record = await getCredential(env, session.gameUid);
        if (!record) throw Object.assign(new Error('GAME_CREDENTIAL_NOT_FOUND'), { status: 409 });
        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
        const token = await decryptGameToken({ ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version }, vaultKey, session.gameUid);
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 30000 });
        try {
          const started = await transport.startCollectorSearch(query, token);
          const job = started?.job || null;
          if (!job?.id) throw Object.assign(new Error('COLLECTOR_JOB_START_INVALID'), { status: 502 });
          await audit(env, session.gameUid, 'radar.collector-search.start', query, { jobId: job.id, cycleId: job.cycleId || null, joined: Boolean(job.joined) });
          return json({ ok: true, job }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/radar/search/status' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const id = String(url.searchParams.get('id') || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('COLLECTOR_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 30000 });
        try {
          const status = await transport.collectorSearchStatus(id);
          const job = status?.job || null;
          if (!job) throw Object.assign(new Error('COLLECTOR_JOB_STATUS_INVALID'), { status: 502 });
          return json({ ok: true, job });
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    s = s.replace(marker, block + marker, 1)
    p.write_text(s)
    print('RADAR_ASYNC_COLLECTOR_PATCH=APPLIED')

# The deployment workflow invokes this script before it overlays live-radar.html.
# Patch a temporary copy using the dedicated UI patcher, then copy the result
# back into the checked-out UI file so the next deployment step installs it.
live_src = Path('radar-ui-live/live-radar.html')
live_tmp = Path('/tmp/wfgg-radar/public/live-radar.html')
if not live_src.is_file():
    raise SystemExit('RADAR_LIVE_SOURCE_MISSING')
live_tmp.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(live_src, live_tmp)
subprocess.run([sys.executable, '.github/scripts/patch-live-radar-async.py'], check=True)
shutil.copyfile(live_tmp, live_src)
print('RADAR_LIVE_ASYNC_OVERLAY=READY')
