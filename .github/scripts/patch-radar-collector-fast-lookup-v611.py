#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
MAIN = CONNECTOR / 'cmd/radar-connector/main.go'
SRC = Path('.radar-release-src/v611-source/connector-go/cmd/radar-connector')
DST = CONNECTOR / 'cmd/radar-connector'


def install_sources() -> None:
    for name in ('collector_fast_lookup_v611.go', 'collector_fast_lookup_v611_test.go'):
        src = SRC / name
        dst = DST / name
        if not src.is_file():
            raise SystemExit(f'V611_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_route() -> None:
    text = MAIN.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_FAST_IDENTITY_ROUTE_V611'
    if marker in text:
        print('RADAR_V611_ROUTE=ALREADY_PRESENT')
        return
    anchor = '\tmux.HandleFunc("GET /v1/collector/index/search", s.signed(s.collectorIndexSearchV610))\n'
    replacement = anchor + '\t// WFGG_RADAR_FAST_IDENTITY_ROUTE_V611\n\tmux.HandleFunc("GET /v1/collector/identity/lookup", s.signed(s.collectorFastLookupV611))\n'
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(f'V611_ROUTE_ANCHOR_COUNT={count}')
    MAIN.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
    print('RADAR_V611_ROUTE=PATCHED')


install_sources()
patch_route()
print('RADAR_FAST_IDENTITY_LOOKUP_V611=READY')
