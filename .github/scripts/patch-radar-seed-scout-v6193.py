#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/cmd/radar-connector/main.go'
SRC = Path('.radar-release-src/v6193-source/connector-go/cmd/radar-connector')
DST = ROOT / 'connector-go/cmd/radar-connector'

for name in ('server_seed_scout_v6193.go', 'server_seed_scout_v6193_test.go'):
    src = SRC / name
    dst = DST / name
    if not src.is_file():
        raise SystemExit(f'V6193_SOURCE_MISSING={src}')
    shutil.copyfile(src, dst)

text = MAIN.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_SEED_SCOUT_ROUTE_V6193'
if marker not in text:
    anchors = [
        '\tmux.HandleFunc("GET /v1/collector/server-cluster-catalog", s.signed(s.serverClusterCatalogV613))\n',
        '\tmux.HandleFunc("GET /v1/collector/server-census", s.signed(s.serverCensusV612))\n',
    ]
    for anchor in anchors:
        if text.count(anchor) == 1:
            addition = anchor + (
                '\t// WFGG_RADAR_SEED_SCOUT_ROUTE_V6193\n'
                '\tmux.HandleFunc("POST /v1/collector/server-seed-scout/start", s.signed(s.serverSeedScoutStartV6193))\n'
                '\tmux.HandleFunc("GET /v1/collector/server-seed-scout/status", s.signed(s.serverSeedScoutStatusV6193))\n'
            )
            MAIN.write_text(text.replace(anchor, addition, 1), encoding='utf-8')
            print('RADAR_V6193_SEED_SCOUT_ROUTE=PATCHED')
            break
    else:
        raise SystemExit('V6193_ROUTE_ANCHOR_MISSING')
else:
    print('RADAR_V6193_SEED_SCOUT_ROUTE=ALREADY_PRESENT')

print('RADAR_V6193_SEED_SCOUT=READY')
