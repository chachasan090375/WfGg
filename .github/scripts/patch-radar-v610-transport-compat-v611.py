#!/usr/bin/env python3
from pathlib import Path

TRANSPORT = Path('/tmp/wfgg-radar/src/game/remote-transport.js')
text = TRANSPORT.read_text(encoding='utf-8')

# The immutable release base still carries the old minimal transport while the
# Worker overlays already use the modern Collector/email methods. Reconstruct
# that established contract first, then let V6.10/V6.11 layer their methods.
required = {
    'startEmailAuth(gameUid, email)': "  startEmailAuth(gameUid, email) { return this.request('/v1/auth/email/start', { body: { gameUid, email } }); }\n",
    'finishEmailAuth(challengeId, code)': "  finishEmailAuth(challengeId, code) { return this.request('/v1/auth/email/finish', { body: { challengeId, code } }); }\n",
    'startCollectorSearch(query, token)': "  startCollectorSearch(query, token) { return this.request('/v1/collector/search/start', { body: { token, query } }); }\n",
    'collectorSearchStatus(id)': "  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }\n",
    'cartographerTick(token)': "  cartographerTick(token) { return this.request('/v1/cartographer/tick', { body: { token } }); }\n",
}

missing = [name for name in required if name not in text]
if not missing:
    print('RADAR_MODERN_TRANSPORT_CONTRACT_V611=ALREADY_PRESENT')
    raise SystemExit(0)

anchor = "  snapshot(token) { return this.request('/v1/snapshot', { body: { token } }); }\n  scanPlayer(query, token) { return this.request('/v1/scan/player', { body: { token, query } }); }\n"
if text.count(anchor) != 1:
    raise SystemExit(f'RADAR_MODERN_TRANSPORT_ANCHOR_COUNT={text.count(anchor)}')

replacement = (
    "  startEmailAuth(gameUid, email) { return this.request('/v1/auth/email/start', { body: { gameUid, email } }); }\n"
    "  finishEmailAuth(challengeId, code) { return this.request('/v1/auth/email/finish', { body: { challengeId, code } }); }\n"
    + anchor +
    "  startCollectorSearch(query, token) { return this.request('/v1/collector/search/start', { body: { token, query } }); }\n"
    "  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }\n"
    "  cartographerTick(token) { return this.request('/v1/cartographer/tick', { body: { token } }); }\n"
)
text = text.replace(anchor, replacement, 1)
TRANSPORT.write_text(text, encoding='utf-8')

for name in required:
    if name not in text:
        raise SystemExit(f'RADAR_MODERN_TRANSPORT_METHOD_MISSING={name}')
print('RADAR_MODERN_TRANSPORT_CONTRACT_V611=PATCHED')
