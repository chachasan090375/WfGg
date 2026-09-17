#!/usr/bin/env python3
from pathlib import Path

TRANSPORT = Path('/tmp/wfgg-radar/src/game/remote-transport.js')
text = TRANSPORT.read_text(encoding='utf-8')
marker = 'collectorIndexSearch(query, limit = 50)'
if marker in text:
    print('RADAR_V610_TRANSPORT_COMPAT=ALREADY_PRESENT')
    raise SystemExit(0)

needle = 'collectorSearchStatus(id)'
if text.count(needle) != 1:
    print(f'RADAR_V610_TRANSPORT_COMPAT_METHOD_COUNT={text.count(needle)}')
    print('RADAR_V610_TRANSPORT_SAFE_SHAPE_BEGIN')
    for no, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if any(token in low for token in ('class remotelastwartransport', 'request(', 'collector', 'cartographer', 'scanplayer', 'health()', 'close()')):
            safe = line.strip()
            if len(safe) > 260:
                safe = safe[:260] + '…'
            print(f'L{no}:{safe}')
    print('RADAR_V610_TRANSPORT_SAFE_SHAPE_END')
    raise SystemExit('RADAR_V610_TRANSPORT_COMPAT_NEEDS_REAL_ANCHOR')
idx = text.index(needle)
line_start = text.rfind('\n', 0, idx) + 1
line_end = text.find('\n', idx)
if line_end < 0:
    line_end = len(text)
    suffix = ''
else:
    suffix = '\n'
line = text[line_start:line_end] + suffix
if '/v1/collector/search/status' not in line or 'this.request' not in line:
    raise SystemExit('RADAR_V610_TRANSPORT_COMPAT_METHOD_SHAPE_INVALID')

addition = line + "  // WFGG_RADAR_COLLECTOR_INDEX_TRANSPORT_V610\n  collectorIndexSearch(query, limit = 50) {\n    const safeLimit = Math.max(1, Math.min(Number(limit) || 50, 100));\n    return this.request(`/v1/collector/index/search?q=${encodeURIComponent(String(query || ''))}&limit=${safeLimit}`, { method: 'GET' });\n  }\n"
TRANSPORT.write_text(text[:line_start] + addition + text[line_end + (1 if suffix else 0):], encoding='utf-8')
print('RADAR_V610_TRANSPORT_COMPAT=PATCHED')
