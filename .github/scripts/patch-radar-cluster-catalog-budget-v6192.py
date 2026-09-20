#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
CATALOG = ROOT / 'connector-go/cmd/radar-connector/server_cluster_catalog_v613.go'

text = CATALOG.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_CLUSTER_CATALOG_BUDGET_V6192'
if marker in text:
    print('RADAR_V6192_CLUSTER_CATALOG_BUDGET=ALREADY_PRESENT')
    raise SystemExit(0)

old = '\tctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)\n'
new = '\t// WFGG_RADAR_CLUSTER_CATALOG_BUDGET_V6192\n\tctx, cancel := context.WithTimeout(r.Context(), 75*time.Second)\n'
count = text.count(old)
if count != 1:
    raise SystemExit(f'V6192_CATALOG_TIMEOUT_ANCHOR_COUNT={count}')

CATALOG.write_text(text.replace(old, new, 1), encoding='utf-8')
print('RADAR_V6192_CLUSTER_CATALOG_BUDGET=PATCHED')
