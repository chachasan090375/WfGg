#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT=Path('/tmp/wfgg-radar')
CATALOG=ROOT/'connector-go/cmd/radar-connector/server_cluster_catalog_v613.go'
JOBS=ROOT/'connector-go/cmd/radar-connector/collector_jobs.go'
SRC=Path('.radar-release-src/v617-source/connector-go/cmd/radar-connector')
DST=ROOT/'connector-go/cmd/radar-connector'

for name in ('server_cycle_quality_v617.go','server_cycle_quality_v617_test.go'):
    src=SRC/name
    if not src.is_file():
        raise SystemExit(f'V617_SOURCE_MISSING={src}')
    shutil.copyfile(src,DST/name)

# Persist future region-isolated sweeps as SUCCESS (data remains usable) with a
# non-empty cycle error marker so they cannot be mistaken for full evidence.
jobs=JOBS.read_text(encoding='utf-8')
job_marker='WFGG_RADAR_PARTIAL_CYCLE_MARKER_V617'
if job_marker not in jobs:
    old='''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })\n\tif err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {\n'''
    new='''\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })\n\t// WFGG_RADAR_PARTIAL_CYCLE_MARKER_V617\n\tcycleErrorV617 := ""\n\tif current, ok := radarCollectorJobs.get(jobID); ok && current.RegionsFailed > 0 {\n\t\tcycleErrorV617 = fmt.Sprintf("PARTIAL_REGIONS_%d", current.RegionsFailed)\n\t}\n\tif err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", cycleErrorV617); err != nil {\n'''
    if jobs.count(old)!=1:
        raise SystemExit(f'V617_JOBS_FINALIZE_ANCHOR_COUNT={jobs.count(old)}')
    JOBS.write_text(jobs.replace(old,new,1),encoding='utf-8')
    print('RADAR_V617_PARTIAL_MARKER=PATCHED')
else:
    print('RADAR_V617_PARTIAL_MARKER=ALREADY_PRESENT')

# Replace the V6.16 catalog derivation with the quality-gated V6.17 derivation.
text=CATALOG.read_text(encoding='utf-8')
marker='WFGG_RADAR_CYCLE_QUALITY_CATALOG_ROUTE_V617'
if marker not in text:
    old='''\t// WFGG_RADAR_HISTORY_BACKED_CLUSTER_CATALOG_ROUTE_V616\n\thistory, err := runServerCycleHistoryV614(ctx, dbPath)\n\tif err != nil {\n\t\twriteJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.16", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_HISTORY_UNAVAILABLE"})\n\t\treturn\n\t}\n\tgraph := serverCycleGraphFromHistoryV616(history)\n\tcensus = serverCensusWithHistoryCyclesV616(census, history)\n\tpayload := markHistoryBackedCatalogV616(deriveServerClusterCatalogV613(census, graph))\n\twriteJSON(w, http.StatusOK, payload)\n'''
    new='''\t// WFGG_RADAR_HISTORY_BACKED_CLUSTER_CATALOG_ROUTE_V616\n\t// WFGG_RADAR_CYCLE_QUALITY_CATALOG_ROUTE_V617\n\thistory, err := runServerCycleHistoryV614(ctx, dbPath)\n\tif err != nil {\n\t\twriteJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.17", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_HISTORY_UNAVAILABLE"})\n\t\treturn\n\t}\n\tquality, err := runCycleQualityMetaV617(ctx, dbPath)\n\tif err != nil {\n\t\twriteJSON(w, http.StatusBadGateway, map[string]any{"ok": false, "catalogVersion": "v6.17", "readonly": true, "error": "SERVER_CLUSTER_CATALOG_QUALITY_UNAVAILABLE"})\n\t\treturn\n\t}\n\tgraph, cycleCountsV617, _, _ := serverCycleGraphFromQualityHistoryV617(history, quality)\n\tcensus = serverCensusWithQualityCyclesV617(census, cycleCountsV617)\n\tpayload := markQualityGatedCatalogV617(deriveServerClusterCatalogV613(census, graph))\n\twriteJSON(w, http.StatusOK, payload)\n'''
    if text.count(old)!=1:
        raise SystemExit(f'V617_CATALOG_HANDLER_ANCHOR_COUNT={text.count(old)}')
    CATALOG.write_text(text.replace(old,new,1),encoding='utf-8')
    print('RADAR_V617_CATALOG_HANDLER=PATCHED')
else:
    print('RADAR_V617_CATALOG_HANDLER=ALREADY_PRESENT')

print('RADAR_CYCLE_QUALITY_GATE_V617=READY')
