#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/main.go')
AUTO = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/autocartographer_v633.go')

s = MAIN.read_text(encoding='utf-8')
marker = 'AUTO_CARTOGRAPHER_V633_ROUTE'
if marker not in s:
    old = '''\tmux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))\n'''
    new = old + '''\t// AUTO_CARTOGRAPHER_V633_ROUTE\n\tmux.HandleFunc("POST /v1/cartographer/tick", s.signed(s.autoCartographerV633TickHTTP))\n'''
    if s.count(old) != 1:
        raise SystemExit(f'AUTO_CARTOGRAPHER_V633_ROUTE_ANCHOR_EXPECTED_1_GOT_{s.count(old)}')
    s = s.replace(old, new, 1)
    MAIN.write_text(s, encoding='utf-8')
    print('AUTO_CARTOGRAPHER_V633_ROUTE=PATCHED')
else:
    print('AUTO_CARTOGRAPHER_V633_ROUTE=ALREADY_PRESENT')

s = AUTO.read_text(encoding='utf-8')
old = 'var autoCartographerV633ProbeRegions = []int{1, 2, 3}\n'
new = 'var autoCartographerV633ProbeRegions = []int{2}\n'
if old in s:
    s = s.replace(old, new, 1)
    AUTO.write_text(s, encoding='utf-8')
    print('AUTO_CARTOGRAPHER_V633_PROBE_REGION=2')
elif new in s:
    print('AUTO_CARTOGRAPHER_V633_PROBE_REGION=ALREADY_2')
else:
    raise SystemExit('AUTO_CARTOGRAPHER_V633_PROBE_ANCHOR_MISSING')

print('AUTO_CARTOGRAPHER_V633_ENDPOINT=/v1/cartographer/tick')
print('AUTO_CARTOGRAPHER_V633_CONFIRMATIONS=2')
