#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT=Path('/tmp/wfgg-radar')
MAIN=ROOT/'connector-go/cmd/radar-connector/main.go'
SRC=Path('.radar-release-src/v614-source/connector-go/cmd/radar-connector')
DST=ROOT/'connector-go/cmd/radar-connector'

for name in ('server_cycle_history_v614.go','server_cycle_history_v614_test.go'):
    src=SRC/name
    if not src.is_file():
        raise SystemExit(f'V614_SOURCE_MISSING={src}')
    shutil.copyfile(src,DST/name)

text=MAIN.read_text(encoding='utf-8')
marker='WFGG_RADAR_SERVER_CYCLE_HISTORY_ROUTE_V614'
if marker not in text:
    anchor='\tmux.HandleFunc("GET /v1/collector/server-cluster-catalog", s.signed(s.serverClusterCatalogV613))\n'
    if text.count(anchor)!=1:
        raise SystemExit(f'V614_ROUTE_ANCHOR_COUNT={text.count(anchor)}')
    addition=anchor+'\t// WFGG_RADAR_SERVER_CYCLE_HISTORY_ROUTE_V614\n\tmux.HandleFunc("GET /v1/collector/server-cycle-history", s.signed(s.serverCycleHistoryV614))\n'
    MAIN.write_text(text.replace(anchor,addition,1),encoding='utf-8')
    print('RADAR_V614_ROUTE=PATCHED')
else:
    print('RADAR_V614_ROUTE=ALREADY_PRESENT')
print('RADAR_SERVER_CYCLE_HISTORY_V614=READY')
