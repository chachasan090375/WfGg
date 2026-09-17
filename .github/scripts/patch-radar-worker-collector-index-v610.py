#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path('/tmp/wfgg-radar')
WORKER = ROOT / 'src/worker.js'
TRANSPORT = ROOT / 'src/game/remote-transport.js'


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


def dump_search_block(text: str) -> None:
    route = "if (url.pathname === '/api/radar/search' && request.method === 'GET')"
    pos = text.find(route)
    if pos < 0:
        pos = text.find('const cached = await searchRadar')
    if pos < 0:
        print('RADAR_V610_SEARCH_BLOCK=NOT_FOUND')
        return
    start = max(0, pos - 300)
    end = min(len(text), pos + 5200)
    snippet = text[start:end]
    # Static source only. Never print environment values or runtime data.
    print('RADAR_V610_SEARCH_BLOCK_BEGIN')
    print(snippet)
    print('RADAR_V610_SEARCH_BLOCK_END')


def patch_worker() -> None:
    text = WORKER.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_COLLECTOR_INDEX_CACHE_V610'
    if marker in text:
        print('RADAR_V610_WORKER=ALREADY_PRESENT')
        return

    pattern = re.compile(
        r"(?P<indent>[ \t]+)const cached = await searchRadar\(env, query, \{ limit \}\);\n"
        r"(?P=indent)if \(!query \|\| cached\.results\.length > 0(?: \|\| session\.role !== ROLES\.OWNER)?\) return json\(cached\);\n\n"
        r"(?P=indent)// Experimental V0\.6 live fallback: OWNER-only until the native READONLY\n"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        dump_search_block(text)
        raise SystemExit(f'worker search anchor: expected exactly 1 match, got {len(matches)}')
    indent = matches[0].group('indent')
    block = f'''{indent}const cached = await searchRadar(env, query, {{ limit }});\n{indent}if (!query || cached.results.length > 0) return json(cached);\n\n{indent}// WFGG_RADAR_COLLECTOR_INDEX_CACHE_V610\n{indent}// The VPS Collector is the canonical accumulated read-only index. Query it\n{indent}// before any live Last War operation, then lazily cache only matching rows in D1.\n{indent}let collectorIndex = {{ attempted: true, status: 'miss', matched: 0, cached: 0 }};\n{indent}const indexTransport = new RemoteLastWarTransport({{ baseUrl: env.RADAR_CONNECTOR_URL, sharedKey: env.RADAR_CONNECTOR_SHARED_KEY, timeoutMs: 30000 }});\n{indent}try {{\n{indent}  const indexed = await indexTransport.collectorIndexSearch(query, limit);\n{indent}  const players = Array.isArray(indexed?.players) ? indexed.players : [];\n{indent}  collectorIndex.matched = players.length;\n{indent}  if (players.length > 0) {{\n{indent}    const stored = await saveRadarPlayerObservations(env, players, {{ sourceCommand: 'collector-index-v610' }});\n{indent}    collectorIndex = {{ attempted: true, status: 'hit', matched: players.length, cached: stored.inserted }};\n{indent}    const refreshed = await searchRadar(env, query, {{ limit }});\n{indent}    return json({{ ...refreshed, collectorIndex }});\n{indent}  }}\n{indent}}} catch (indexError) {{\n{indent}  collectorIndex = {{ attempted: true, status: 'unavailable', matched: 0, cached: 0, error: String(indexError?.message || 'COLLECTOR_INDEX_UNAVAILABLE') }};\n{indent}}} finally {{\n{indent}  await indexTransport.close().catch(() => {{}});\n{indent}}}\n\n{indent}// Non-OWNER users stop here: a Collector miss must never trigger a live game scan.\n{indent}if (session.role !== ROLES.OWNER) return json({{ ...cached, collectorIndex }});\n\n{indent}// Experimental V0.6 live fallback: OWNER-only until the native READONLY\n'''
    text = text[:matches[0].start()] + block + text[matches[0].end():]
    WORKER.write_text(text, encoding='utf-8')
    print('RADAR_V610_WORKER=PATCHED')


patch_transport()
patch_worker()
print('RADAR_COLLECTOR_INDEX_WORKER_V610=READY')
