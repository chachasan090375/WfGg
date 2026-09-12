#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/main.go')
s = MAIN.read_text(encoding='utf-8')
marker = 'AUTO_CARTOGRAPHER_V633_ROUTE'
if marker in s:
    print('AUTO_CARTOGRAPHER_V633_ROUTE=ALREADY_PRESENT')
    raise SystemExit(0)

old = '''\tmux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))\n'''
new = old + '''\t// AUTO_CARTOGRAPHER_V633_ROUTE\n\tmux.HandleFunc("POST /v1/cartographer/tick", s.signed(s.autoCartographerV633TickHTTP))\n'''
if s.count(old) != 1:
    raise SystemExit(f'AUTO_CARTOGRAPHER_V633_ROUTE_ANCHOR_EXPECTED_1_GOT_{s.count(old)}')
s = s.replace(old, new, 1)
MAIN.write_text(s, encoding='utf-8')
print('AUTO_CARTOGRAPHER_V633_ROUTE=PATCHED')
print('AUTO_CARTOGRAPHER_V633_ENDPOINT=/v1/cartographer/tick')
