#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT=Path('/tmp/wfgg-radar')
MAIN=ROOT/'connector-go/cmd/radar-connector/main.go'
SRC=Path('.radar-release-src/v6122-source/connector-go/cmd/radar-connector')
DST=ROOT/'connector-go/cmd/radar-connector'

for name in ('server_cycle_map_v6122.go','server_cycle_map_v6122_test.go'):
    src=SRC/name
    if not src.is_file(): raise SystemExit(f'V6122_SOURCE_MISSING={src}')
    shutil.copyfile(src,DST/name)

text=MAIN.read_text(encoding='utf-8')
marker='WFGG_RADAR_SERVER_CYCLE_MAP_ROUTE_V6122'
if marker not in text:
    anchor='\tmux.HandleFunc("GET /v1/collector/server-census", s.signed(s.serverCensusV612))\n'
    if text.count(anchor)!=1:
        raise SystemExit(f'V6122_ROUTE_ANCHOR_COUNT={text.count(anchor)}')
    addition=anchor+'\t// WFGG_RADAR_SERVER_CYCLE_MAP_ROUTE_V6122\n\tmux.HandleFunc("GET /v1/collector/server-cycle-map", s.signed(s.serverCycleMapV6122))\n'
    MAIN.write_text(text.replace(anchor,addition,1),encoding='utf-8')
    print('RADAR_V6122_ROUTE=PATCHED')
else:
    print('RADAR_V6122_ROUTE=ALREADY_PRESENT')
print('RADAR_SERVER_CYCLE_MAP_V6122=READY')
