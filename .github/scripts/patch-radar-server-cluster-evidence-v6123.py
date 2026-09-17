#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT=Path('/tmp/wfgg-radar')
MAIN=ROOT/'connector-go/cmd/radar-connector/main.go'
SRC=Path('.radar-release-src/v6123-source/connector-go/cmd/radar-connector')
DST=ROOT/'connector-go/cmd/radar-connector'

for name in ('server_cluster_evidence_v6123.go','server_cluster_evidence_v6123_test.go'):
    src=SRC/name
    if not src.is_file():
        raise SystemExit(f'V6123_SOURCE_MISSING={src}')
    shutil.copyfile(src,DST/name)

text=MAIN.read_text(encoding='utf-8')
marker='WFGG_RADAR_SERVER_CLUSTER_EVIDENCE_ROUTE_V6123'
if marker not in text:
    anchor='\tmux.HandleFunc("GET /v1/collector/server-cycle-map", s.signed(s.serverCycleMapV6122))\n'
    if text.count(anchor)!=1:
        raise SystemExit(f'V6123_ROUTE_ANCHOR_COUNT={text.count(anchor)}')
    addition=anchor+'\t// WFGG_RADAR_SERVER_CLUSTER_EVIDENCE_ROUTE_V6123\n\tmux.HandleFunc("GET /v1/collector/server-cluster-evidence", s.signed(s.serverClusterEvidenceV6123))\n'
    MAIN.write_text(text.replace(anchor,addition,1),encoding='utf-8')
    print('RADAR_V6123_ROUTE=PATCHED')
else:
    print('RADAR_V6123_ROUTE=ALREADY_PRESENT')
print('RADAR_SERVER_CLUSTER_EVIDENCE_V6123=READY')
