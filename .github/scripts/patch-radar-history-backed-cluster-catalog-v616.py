#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT=Path('/tmp/wfgg-radar')
CATALOG=ROOT/'connector-go/cmd/radar-connector/server_cluster_catalog_v613.go'
SRC=Path('.radar-release-src/v616-source/connector-go/cmd/radar-connector')
DST=ROOT/'connector-go/cmd/radar-connector'

for name in ('server_cluster_catalog_history_v616.go','server_cluster_catalog_history_v616_test.go'):
    src=SRC/name
    if not src.is_file():
        raise SystemExit(f'V616_SOURCE_MISSING={src}')
    shutil.copyfile(src,DST/name)

text=CATALOG.read_text(encoding='utf-8')
marker='WFGG_RADAR_HISTORY_BACKED_CLUSTER_CATALOG_ROUTE_V616'
if marker not in text:
    old='''\tgraph, err := runServerCycleMapV6122(ctx, dbPath)\n\tif err != nil {\n\t\twriteJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.13", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_GRAPH_UNAVAILABLE"})\n\t\treturn\n\t}\n\twriteJSON(w, http.StatusOK, deriveServerClusterCatalogV613(census, graph))\n'''
    new='''\t// WFGG_RADAR_HISTORY_BACKED_CLUSTER_CATALOG_ROUTE_V616\n\thistory, err := runServerCycleHistoryV614(ctx, dbPath)\n\tif err != nil {\n\t\twriteJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.16", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_HISTORY_UNAVAILABLE"})\n\t\treturn\n\t}\n\tgraph := serverCycleGraphFromHistoryV616(history)\n\tcensus = serverCensusWithHistoryCyclesV616(census, history)\n\tpayload := markHistoryBackedCatalogV616(deriveServerClusterCatalogV613(census, graph))\n\twriteJSON(w, http.StatusOK, payload)\n'''
    if text.count(old)!=1:
        raise SystemExit(f'V616_CATALOG_HANDLER_ANCHOR_COUNT={text.count(old)}')
    CATALOG.write_text(text.replace(old,new,1),encoding='utf-8')
    print('RADAR_V616_CATALOG_HANDLER=PATCHED')
else:
    print('RADAR_V616_CATALOG_HANDLER=ALREADY_PRESENT')

print('RADAR_HISTORY_BACKED_CLUSTER_CATALOG_V616=READY')
