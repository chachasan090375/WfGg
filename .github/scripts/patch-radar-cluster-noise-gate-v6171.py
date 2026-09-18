#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
CATALOG = ROOT / 'connector-go/cmd/radar-connector/server_cluster_catalog_v613.go'
SRC = Path('.radar-release-src/v6171-source/connector-go/cmd/radar-connector')
DST = ROOT / 'connector-go/cmd/radar-connector'

for name in ('server_cluster_noise_gate_v6171.go', 'server_cluster_noise_gate_v6171_test.go'):
    src = SRC / name
    if not src.is_file():
        raise SystemExit(f'V6171_SOURCE_MISSING={src}')
    shutil.copyfile(src, DST / name)

text = CATALOG.read_text(encoding='utf-8')
marker = 'WFGG_RADAR_CLUSTER_NOISE_GATE_ROUTE_V6171'
if marker not in text:
    old = '''	payload := markQualityGatedCatalogV617(deriveServerClusterCatalogV613(census, graph))
	writeJSON(w, http.StatusOK, payload)
'''
    new = '''	// WFGG_RADAR_CLUSTER_NOISE_GATE_ROUTE_V6171
	payload := deriveServerClusterCatalogV6171(census, graph)
	writeJSON(w, http.StatusOK, payload)
'''
    if text.count(old) != 1:
        raise SystemExit(f'V6171_CATALOG_ANCHOR_COUNT={text.count(old)}')
    CATALOG.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RADAR_V6171_CATALOG_HANDLER=PATCHED')
else:
    print('RADAR_V6171_CATALOG_HANDLER=ALREADY_PRESENT')

print('RADAR_CLUSTER_NOISE_GATE_V6171=READY')
