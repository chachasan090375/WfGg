#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path('/tmp/wfgg-radar')
WORKER = ROOT / 'src/worker.js'
TRANSPORT = ROOT / 'src/game/remote-transport.js'
REPOSITORY = ROOT / 'src/db/repository.js'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def patch_transport() -> None:
    text = TRANSPORT.read_text(encoding='utf-8')
    marker = 'collectorIndexSearch(query, limit = 50)'
    if marker in text:
        print('RADAR_V610_TRANSPORT=ALREADY_PRESENT')
        return
    old = '''  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }\n  cartographerTick(token) { return this.request('/v1/cartographer/tick', { body: { token } }); }\n'''
    new = '''  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }\n  // WFGG_RADAR_COLLECTOR_INDEX_TRANSPORT_V610\n  collectorIndexSearch(query, limit = 50) {\n    const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 100));\n    return this.request(`/v1/collector/index/search?q=${encodeURIComponent(String(query || ''))}&limit=${safeLimit}`, { method: 'GET' });\n  }\n  cartographerTick(token) { return this.request('/v1/cartographer/tick', { body: { token } }); }\n'''
    TRANSPORT.write_text(replace_once(text, old, new, 'transport anchor'), encoding='utf-8')
    print('RADAR_V610_TRANSPORT=PATCHED')


def patch_repository_writer() -> None:
    text = REPOSITORY.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_D1_OBSERVATION_WRITER_V6101'
    if marker in text:
        print('RADAR_V6101_D1_WRITER=ALREADY_PRESENT')
        return
    addition = r'''

// WFGG_RADAR_D1_OBSERVATION_WRITER_V6101
// Minimal immutable-release writer used by the V6.10 Collector-index lazy cache.
// It stores only normalized Radar observation fields; no token, credential or raw payload.
export async function saveRadarPlayerObservations(env, players = [], { sourceCommand = 'collector-index-v610', rawRef = null } = {}) {
  if (!env?.DB) throw Object.assign(new Error('RADAR_DB_NOT_CONFIGURED'), { status: 503 });
  const safe = Array.isArray(players) ? players.slice(0, 100) : [];
  let inserted = 0;
  const intOrNull = value => (value === null || value === undefined || value === '')
    ? null
    : (Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : null);
  for (const player of safe) {
    const pseudo = String(player?.pseudo || '').trim();
    const subjectUid = player?.gameUid ? String(player.gameUid).trim() : null;
    if (!pseudo && !subjectUid) continue;
    const observedAt = String(player?.observedAt || new Date().toISOString());
    await env.DB.prepare(`
      INSERT INTO radar_observations(
        subject_uid, pseudo, server_id, alliance_id, alliance_tag,
        x, y, hq_level, power, shield_state,
        observed_at, source_command, raw_ref
      ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    `).bind(
      subjectUid,
      pseudo || null,
      player?.serverId ? String(player.serverId) : null,
      player?.allianceId ? String(player.allianceId) : null,
      player?.allianceTag ? String(player.allianceTag) : null,
      intOrNull(player?.x), intOrNull(player?.y), intOrNull(player?.hqLevel), intOrNull(player?.power),
      player?.shieldState == null ? null : String(player.shieldState),
      observedAt, String(sourceCommand || 'collector-index-v610'), rawRef ? String(rawRef) : null
    ).run();
    inserted++;
  }
  return { inserted };
}
'''
    REPOSITORY.write_text(text.rstrip() + addition + '\n', encoding='utf-8')
    print('RADAR_V6101_D1_WRITER=PATCHED')


def ensure_repository_import(text: str) -> str:
    if re.search(r"import\s*\{[^}]*\bsaveRadarPlayerObservations\b[^}]*\}\s*from\s*['\"]\./db/repository\.js['\"]", text, re.S):
        return text
    pattern = re.compile(r"import\s*\{(?P<body>[^}]*)\}\s*from\s*'\./db/repository\.js';")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise SystemExit(f'repository import: expected exactly 1 match, got {len(matches)}')
    body = matches[0].group('body').strip()
    body = body + (', ' if body else '') + 'saveRadarPlayerObservations'
    replacement = "import { " + body + " } from './db/repository.js';"
    return text[:matches[0].start()] + replacement + text[matches[0].end():]


def patch_worker() -> None:
    text = WORKER.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_COLLECTOR_INDEX_CACHE_V610'
    if marker in text:
        print('RADAR_V610_WORKER=ALREADY_PRESENT')
        return

    text = ensure_repository_import(text)
    old = '''      if (url.pathname === '/api/radar/search' && request.method === 'GET') {\n        const session = await requireSession(request, env);\n        assertCapability(session.role, 'radar.search');\n        return json(await searchRadar(env, url.searchParams.get('q') || '', { limit: url.searchParams.get('limit') || 50 }));\n      }\n'''
    new = '''      if (url.pathname === '/api/radar/search' && request.method === 'GET') {\n        const session = await requireSession(request, env);\n        assertCapability(session.role, 'radar.search');\n        const query = String(url.searchParams.get('q') || '').trim();\n        const limit = url.searchParams.get('limit') || 50;\n        const cached = await searchRadar(env, query, { limit });\n        if (!query || cached.results.length > 0) return json(cached);\n\n        // WFGG_RADAR_COLLECTOR_INDEX_CACHE_V610\n        // The VPS Collector is the canonical accumulated read-only index. Query it\n        // before any live Last War operation, then lazily cache only matching rows in D1.\n        let collectorIndex = { attempted: true, status: 'miss', matched: 0, cached: 0 };\n        const indexTransport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 30000 });\n        try {\n          const indexed = await indexTransport.collectorIndexSearch(query, limit);\n          const players = Array.isArray(indexed?.players) ? indexed.players : [];\n          collectorIndex.matched = players.length;\n          if (players.length > 0) {\n            const stored = await saveRadarPlayerObservations(env, players, { sourceCommand: 'collector-index-v610' });\n            collectorIndex = { attempted: true, status: 'hit', matched: players.length, cached: stored.inserted };\n            const refreshed = await searchRadar(env, query, { limit });\n            return json({ ...refreshed, collectorIndex });\n          }\n        } catch (indexError) {\n          collectorIndex = { attempted: true, status: 'unavailable', matched: 0, cached: 0, error: String(indexError?.message || 'COLLECTOR_INDEX_UNAVAILABLE') };\n        } finally {\n          await indexTransport.close().catch(() => {});\n        }\n\n        // Non-OWNER users stop here: a Collector miss must never trigger a live game scan.\n        if (session.role !== ROLES.OWNER) return json({ ...cached, collectorIndex });\n\n        // Last-resort read-only Last War lookup for OWNER only.\n        const record = await getCredential(env, session.gameUid);\n        if (!record) return json({ ...cached, collectorIndex, liveScan: { attempted: false, status: 'credential-missing' } });\n        const vaultKey = requireSecret(env.RADAR_TOKEN_VAULT_KEY, 'RADAR_TOKEN_VAULT_KEY');\n        const token = await decryptGameToken({ ciphertext: record.ciphertext, iv: record.iv, keyVersion: record.key_version }, vaultKey, session.gameUid);\n        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY });\n        try {\n          const result = await transport.scanPlayer(query, token);\n          const players = Array.isArray(result?.players) ? result.players : [];\n          const stored = await saveRadarPlayerObservations(env, players, { sourceCommand: 'native-template-player-scan-v2' });\n          await audit(env, session.gameUid, 'radar.live-player-scan', query, { observedPlayers: players.length, inserted: stored.inserted });\n          const refreshed = await searchRadar(env, query, { limit });\n          return json({ ...refreshed, collectorIndex, liveScan: { attempted: true, status: 'ok', observedPlayers: players.length, inserted: stored.inserted } });\n        } catch (error) {\n          const code = String(error?.message || 'LASTWAR_PLAYER_SCAN_FAILED');\n          return json({ ...cached, collectorIndex, liveScan: { attempted: true, status: 'unavailable', error: code } });\n        } finally {\n          await transport.close().catch(() => {});\n        }\n      }\n'''
    WORKER.write_text(replace_once(text, old, new, 'actual reconstructed worker search route'), encoding='utf-8')
    print('RADAR_V610_WORKER=PATCHED')


patch_transport()
patch_repository_writer()
patch_worker()
print('RADAR_COLLECTOR_INDEX_WORKER_V610=READY')
print('RADAR_D1_OBSERVATION_WRITER_V6101=READY')
