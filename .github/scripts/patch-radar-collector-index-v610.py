#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
MAIN = CONNECTOR / 'cmd/radar-connector/main.go'
SRC = Path('.radar-release-src/v610-source/connector-go/cmd/radar-connector')
DST = CONNECTOR / 'cmd/radar-connector'


def install_sources() -> None:
    for name in ('collector_index_v610.go', 'collector_index_v610_test.go'):
        src = SRC / name
        dst = DST / name
        if not src.is_file():
            raise SystemExit(f'V610_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_route() -> None:
    text = MAIN.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_COLLECTOR_INDEX_ROUTE_V610'
    if marker in text:
        print('RADAR_V610_ROUTE=ALREADY_PRESENT')
        return
    anchor = '\tmux.HandleFunc("GET /v1/collector/audit", s.signed(s.collectorAuditV699))\n'
    replacement = anchor + '\t// WFGG_RADAR_COLLECTOR_INDEX_ROUTE_V610\n\tmux.HandleFunc("GET /v1/collector/index/search", s.signed(s.collectorIndexSearchV610))\n'
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(f'V610_ROUTE_ANCHOR_COUNT={count}')
    MAIN.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
    print('RADAR_V610_ROUTE=PATCHED')


install_sources()
patch_route()
print('RADAR_COLLECTOR_INDEX_V610=READY')
