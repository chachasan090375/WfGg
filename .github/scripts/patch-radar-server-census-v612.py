#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CONNECTOR = ROOT / 'connector-go'
MAIN = CONNECTOR / 'cmd/radar-connector/main.go'
SRC = Path('.radar-release-src/v612-source/connector-go/cmd/radar-connector')
DST = CONNECTOR / 'cmd/radar-connector'


def install_sources() -> None:
    for name in ('server_census_v612.go', 'server_census_v612_test.go'):
        src = SRC / name
        dst = DST / name
        if not src.is_file():
            raise SystemExit(f'V612_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_route() -> None:
    text = MAIN.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_SERVER_CENSUS_ROUTE_V612'
    if marker in text:
        print('RADAR_V612_ROUTE=ALREADY_PRESENT')
        return
    anchors = [
        '\tmux.HandleFunc("GET /v1/collector/audit", s.signed(s.collectorAuditV699))\n',
        '\tmux.HandleFunc("GET /v1/collector/identity/lookup", s.signed(s.collectorFastLookupV611))\n',
    ]
    for anchor in anchors:
        if text.count(anchor) == 1:
            replacement = anchor + '\t// WFGG_RADAR_SERVER_CENSUS_ROUTE_V612\n\tmux.HandleFunc("GET /v1/collector/server-census", s.signed(s.serverCensusV612))\n'
            MAIN.write_text(text.replace(anchor, replacement, 1), encoding='utf-8')
            print('RADAR_V612_ROUTE=PATCHED')
            return
    raise SystemExit('V612_ROUTE_ANCHOR_MISSING')


install_sources()
patch_route()
print('RADAR_SERVER_CENSUS_V612=READY')
