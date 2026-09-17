#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
MAIN = CONNECTOR / 'cmd/radar-connector/main.go'
SRC = Path('.radar-release-src/v699-source/connector-go/cmd/radar-connector')
DST = CONNECTOR / 'cmd/radar-connector'


def install_sources() -> None:
    for name in ('collector_live_audit_v699.go', 'collector_live_audit_v699_test.go'):
        src = SRC / name
        dst = DST / name
        if not src.is_file():
            raise SystemExit(f'V699_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_route() -> None:
    text = MAIN.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_COLLECTOR_LIVE_AUDIT_ROUTE_V699'
    if marker in text:
        print('RADAR_V699_ROUTE=ALREADY_PRESENT')
        return
    anchor = '\tmux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))\n'
    replacement = anchor + '\t// WFGG_RADAR_COLLECTOR_LIVE_AUDIT_ROUTE_V699\n\tmux.HandleFunc("GET /v1/collector/audit", s.signed(s.collectorAuditV699))\n'
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(f'V699_ROUTE_ANCHOR_COUNT={count}')
    MAIN.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
    print('RADAR_V699_ROUTE=PATCHED')


install_sources()
patch_route()
print('RADAR_COLLECTOR_LIVE_AUDIT_V699=READY')
