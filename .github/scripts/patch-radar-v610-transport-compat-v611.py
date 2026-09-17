#!/usr/bin/env python3
from pathlib import Path

TRANSPORT = Path('/tmp/wfgg-radar/src/game/remote-transport.js')
text = TRANSPORT.read_text(encoding='utf-8')
marker = 'collectorIndexSearch(query, limit = 50)'
if marker in text:
    print('RADAR_V610_TRANSPORT_COMPAT=ALREADY_PRESENT')
    raise SystemExit(0)

needle = "  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }\n"
count = text.count(needle)
if count != 1:
    raise SystemExit(f'RADAR_V610_TRANSPORT_COMPAT_ANCHOR_COUNT={count}')
addition = needle + "  // WFGG_RADAR_COLLECTOR_INDEX_TRANSPORT_V610\n  collectorIndexSearch(query, limit = 50) {\n    const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 100));\n    return this.request(`/v1/collector/index/search?q=${encodeURIComponent(String(query || ''))}&limit=${safeLimit}`, { method: 'GET' });\n  }\n"
TRANSPORT.write_text(text.replace(needle, addition, 1), encoding='utf-8')
print('RADAR_V610_TRANSPORT_COMPAT=PATCHED')
