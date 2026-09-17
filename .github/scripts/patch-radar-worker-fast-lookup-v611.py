#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
WORKER = ROOT / 'src/worker.js'
TRANSPORT = ROOT / 'src/game/remote-transport.js'


def patch_transport() -> None:
    text = TRANSPORT.read_text(encoding='utf-8')
    marker = 'collectorFastLookup(query, server = \'\')'
    if marker in text:
        print('RADAR_V611_TRANSPORT=ALREADY_PRESENT')
        return
    anchor = '''  collectorIndexSearch(query, limit = 50) {\n    const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 100));\n    return this.request(`/v1/collector/index/search?q=${encodeURIComponent(String(query || ''))}&limit=${safeLimit}`, { method: 'GET' });\n  }\n'''
    addition = anchor + '''  // WFGG_RADAR_FAST_IDENTITY_TRANSPORT_V611\n  collectorFastLookup(query, server = '') {\n    const q = encodeURIComponent(String(query || ''));\n    const s = String(server || '').trim();\n    return this.request(`/v1/collector/identity/lookup?q=${q}${s ? `&server=${encodeURIComponent(s)}` : ''}`, { method: 'GET' });\n  }\n'''
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(f'V611_TRANSPORT_ANCHOR_COUNT={count}')
    TRANSPORT.write_text(text.replace(anchor, addition, 1), encoding='utf-8')
    print('RADAR_V611_TRANSPORT=PATCHED')


def patch_worker() -> None:
    text = WORKER.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_FAST_LOOKUP_ROUTE_V611'
    if marker in text:
        print('RADAR_V611_WORKER=ALREADY_PRESENT')
        return

    start_marker = "      if (url.pathname === '/api/radar/search' && request.method === 'GET') {"
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit('V611_SEARCH_ROUTE_START_MISSING')
    next_route = text.find("\n      if (url.pathname === ", start + len(start_marker))
    if next_route < 0:
        raise SystemExit('V611_SEARCH_ROUTE_END_MISSING')

    block = r'''      // WFGG_RADAR_FAST_LOOKUP_ROUTE_V611
      if (url.pathname === '/api/radar/search' && request.method === 'GET') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const query = String(url.searchParams.get('q') || '').trim();
        const limit = url.searchParams.get('limit') || 50;
        const cached = await searchRadar(env, query, { limit });
        if (!query || cached.results.length > 0) {
          return json({ ...cached, fastLookup: { attempted: false, status: cached.results.length ? 'd1-hit' : 'empty', source: 'd1' } });
        }

        const startedAt = Date.now();
        const transport = new RemoteLastWarTransport({ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 10000 });
        try {
          const exact = await transport.collectorFastLookup(query);
          if (exact?.resolved && exact?.player) {
            const stored = await saveRadarPlayerObservations(env, [exact.player], { sourceCommand: 'collector-fast-identity-v611' });
            const refreshed = await searchRadar(env, query, { limit });
            return json({
              ...refreshed,
              fastLookup: {
                attempted: true, status: 'exact-hit', source: 'identity-index', route: String(exact.route || 'EXACT_PLAYER'),
                matched: 1, cached: stored.inserted, elapsedMs: Date.now() - startedAt
              }
            });
          }
          if (exact?.ambiguous) {
            return json({
              ...cached,
              fastLookup: {
                attempted: true, status: 'ambiguous', source: 'identity-index', route: String(exact.route || 'AMBIGUOUS'),
                candidateCount: Number(exact.candidateCount || 0), elapsedMs: Date.now() - startedAt
              },
              refreshAvailable: false
            });
          }

          // Local fuzzy fallback only. This still queries the persisted Collector index;
          // it never starts a map/profile cycle and never contacts Last War.
          const indexed = await transport.collectorIndexSearch(query, limit);
          const players = Array.isArray(indexed?.players) ? indexed.players : [];
          if (players.length > 0) {
            const stored = await saveRadarPlayerObservations(env, players, { sourceCommand: 'collector-index-fuzzy-v611' });
            const refreshed = await searchRadar(env, query, { limit });
            return json({
              ...refreshed,
              fastLookup: {
                attempted: true, status: 'fuzzy-hit', source: 'collector-index', route: 'FUZZY_LOCAL',
                matched: players.length, cached: stored.inserted, elapsedMs: Date.now() - startedAt
              }
            });
          }

          return json({
            ...cached,
            fastLookup: { attempted: true, status: 'miss', source: 'identity-index', route: String(exact?.route || 'MISS'), elapsedMs: Date.now() - startedAt },
            refreshAvailable: session.role === ROLES.OWNER
          });
        } catch (error) {
          return json({
            ...cached,
            fastLookup: { attempted: true, status: 'unavailable', source: 'identity-index', error: String(error?.message || 'FAST_LOOKUP_UNAVAILABLE'), elapsedMs: Date.now() - startedAt },
            refreshAvailable: session.role === ROLES.OWNER
          });
        } finally {
          await transport.close().catch(() => {});
        }
      }
'''

    WORKER.write_text(text[:start] + block + text[next_route:], encoding='utf-8')
    print('RADAR_V611_WORKER=PATCHED')


patch_transport()
patch_worker()
print('RADAR_FAST_LOOKUP_WORKER_V611=READY')
