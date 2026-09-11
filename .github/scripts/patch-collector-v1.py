#!/usr/bin/env python3
from pathlib import Path

V4 = Path('/tmp/wfgg-radar/connector-go/native-template/player_scan_v4.go')

text = V4.read_text(encoding='utf-8')
old = '''\t\tif profileTemplate != nil {\n\t\t\tp, ok, err := requestProfileV3(conn, profileTemplate, players[i].GameUID, observedAt)\n\t\t\tif err != nil {\n\t\t\t\treturn nil, err\n\t\t\t}\n\t\t\tif ok {\n\t\t\t\tmergePlayerProfileV3(&players[i], p)\n\t\t\t}\n\t\t}\n'''
new = '''\t\tif profileTemplate != nil {\n\t\t\tp, ok, err := requestProfileV3(conn, profileTemplate, players[i].GameUID, observedAt)\n\t\t\tif err != nil {\n\t\t\t\t// Collector V1 keeps a valid map hit even when optional profile\n\t\t\t\t// enrichment is unavailable or times out.\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tif ok {\n\t\t\t\tmergePlayerProfileV3(&players[i], p)\n\t\t\t}\n\t\t}\n'''
if text.count(old) != 1:
    raise SystemExit(f'collector profile patch: expected 1 match, got {text.count(old)}')
V4.write_text(text.replace(old, new, 1), encoding='utf-8')
print('COLLECTOR_V1_PROFILE_ENRICHMENT=BEST_EFFORT')
