#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess
import sys

p = Path('/tmp/wfgg-radar/src/worker.js')
s = p.read_text()
search_marker = "      if (url.pathname === '/api/radar/search' && request.method === 'GET') {"

if "'/api/radar/search/start'" in s:
    print('RADAR_ASYNC_COLLECTOR_PATCH=ALREADY_PRESENT')
else:
    if search_marker not in s:
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
    s = s.replace(search_marker, block + search_marker, 1)
    print('RADAR_ASYNC_COLLECTOR_PATCH=APPLIED')

auth_marker = "      if (url.pathname === '/api/me' && request.method === 'GET') {"
if "'/api/auth/lastwar/start'" in s:
    print('RADAR_EMAIL_AUTH_WORKER_PATCH=ALREADY_PRESENT')
else:
    if auth_marker not in s:
        raise SystemExit('RADAR_EMAIL_AUTH_WORKER_ANCHOR_MISSING')
    auth_block = r'''      if (url.pathname === '/api/auth/lastwar/start' && request.method === 'POST') {
        const body = await bodyJson(request);
        const gameUid = String(body.gameUid || '').trim();
        const email = String(body.email || '').trim();
        if (!/^\d{6,64}$/.test(gameUid)) throw Object.assign(new Error('LASTWAR_GAME_UID_REQUIRED'), { status: 400 });
        if (!email || email.length > 320 || !email.includes('@')) throw Object.assign(new Error('LASTWAR_EMAIL_INVALID'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 40000 });
        try {
          const started = await transport.startEmailAuth(gameUid, email);
          const challengeId = String(started?.challengeId || '').trim();
          if (!challengeId) throw Object.assign(new Error('LASTWAR_EMAIL_CHALLENGE_INVALID'), { status: 502 });
          return json({ ok: true, challengeId, expiresIn: Number(started?.expiresIn || 600) }, 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

      if (url.pathname === '/api/auth/lastwar/finish' && request.method === 'POST') {
        const body = await bodyJson(request);
        const challengeId = String(body.challengeId || '').trim();
        const code = String(body.code || '').trim();
        if (!/^[A-Za-z0-9_-]{8,128}$/.test(challengeId)) throw Object.assign(new Error('LASTWAR_EMAIL_CHALLENGE_REQUIRED'), { status: 400 });
        if (!/^\d{6}$/.test(code)) throw Object.assign(new Error('LASTWAR_EMAIL_CODE_INVALID'), { status: 400 });
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 70000 });
        try {
          const completed = await transport.finishEmailAuth(challengeId, code);
          const credential = String(completed?.auth?.credential || '');
          const rawIdentity = completed?.auth?.identity || null;
          if (credential.length < 8 || !rawIdentity?.gameUid) throw Object.assign(new Error('LASTWAR_EMAIL_AUTH_RESULT_INVALID'), { status: 502 });
          if (!rawIdentity?.pseudo || !rawIdentity?.serverId) throw Object.assign(new Error('LASTWAR_IDENTITY_NOT_IN_COLLECTOR'), { status: 409 });
          const identity = normalizeIdentity(rawIdentity);
          await ensureBootstrapOwnerGrant(env, identity);
          const user = await bindIdentityToGrant(env, identity);
          const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');
          const encrypted = await encryptGameToken(credential, vaultKey, identity.gameUid);
          await saveCredential(env, identity.gameUid, encrypted);
          await audit(env, identity.gameUid, 'auth.lastwar-email.success', identity.gameUid, { serverId: identity.serverId, connector: 'lastwar-email-code' });
          const sessionKey = requireSecret(env.RADAR_SESSION_KEY, 'RADAR_SESSION_KEY');
          const ttl = Math.max(900, Math.min(Number(env.RADAR_SESSION_TTL || 3600), 43200));
          const session = await createSession({ gameUid: identity.gameUid, pseudo: identity.pseudo, serverId: identity.serverId, role: user.role }, sessionKey, ttl);
          return json({ ok: true, user: { gameUid: identity.gameUid, pseudo: identity.pseudo, serverId: identity.serverId, role: user.role } }, 200, { 'set-cookie': sessionCookie(session, ttl) });
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    s = s.replace(auth_marker, auth_block + auth_marker, 1)
    print('RADAR_EMAIL_AUTH_WORKER_PATCH=APPLIED')

p.write_text(s)
print('RADAR_EMAIL_AUTH_PATCHER=V1')

# V6.3.3: extend the existing autonomous scheduled cycle with the
# credential-vault-backed Auto-Cartographer. The game token is decrypted only
# inside the Worker tick and is never persisted by the VPS connector.
subprocess.run([sys.executable, '.github/scripts/patch-radar-autocartographer-worker-v633.py'], check=True)
print('AUTO_CARTOGRAPHER_WORKER_V633_CHAIN=READY')

# The deployment workflow invokes this script before it overlays live-radar.html.
# Patch a temporary copy using the dedicated UI patchers, then copy the result
# back into the checked-out UI file so the next deployment step installs it.
live_src = Path('radar-ui-live/live-radar.html')
live_tmp = Path('/tmp/wfgg-radar/public/live-radar.html')
if not live_src.is_file():
    raise SystemExit('RADAR_LIVE_SOURCE_MISSING')
live_tmp.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(live_src, live_tmp)
subprocess.run([sys.executable, '.github/scripts/patch-live-radar-async.py'], check=True)
subprocess.run([sys.executable, '.github/scripts/patch-live-radar-email-auth.py'], check=True)
shutil.copyfile(live_tmp, live_src)
print('RADAR_LIVE_ASYNC_EMAIL_AUTH_OVERLAY=READY')
