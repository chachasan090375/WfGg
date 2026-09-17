#!/usr/bin/env python3
from pathlib import Path

MARKER = 'WFGG_RADAR_REGION_ISOLATION_V66'

collector = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
if collector.is_file():
    s = collector.read_text(encoding='utf-8')
    if MARKER in s:
        print('RADAR_V66_REGION_ISOLATION=ALREADY_PRESENT')
    elif 'WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65' not in s or 'func (s *server) runCollectorSearch' not in s:
        # Web-release compatibility shim: Worker/UI staging does not carry the
        # full VPS connector source tree. Do not invent runtime logic there.
        print('RADAR_V66_REGION_ISOLATION=SKIPPED_WEB_SHIM')
    else:
        field_anchor = '\tAuthState       string         `json:"authState,omitempty"`\n\tStartedAt       string         `json:"startedAt"`\n'
        field_repl = '\tAuthState        string                   `json:"authState,omitempty"`\n\tRegionsCompleted int                      `json:"regionsCompleted,omitempty"`\n\tRegionsFailed    int                      `json:"regionsFailed,omitempty"`\n\tRegionFailures   []collectorRegionFailure `json:"regionFailures,omitempty"`\n\tStartedAt        string                   `json:"startedAt"`\n'
        if s.count(field_anchor) != 1:
            raise SystemExit('V66_FIELDS_ANCHOR_MISSING')
        s = s.replace(field_anchor, field_repl, 1)

        store_anchor = 'type collectorJobStore struct {\n'
        region_type = '''// WFGG_RADAR_REGION_ISOLATION_V66\ntype collectorRegionFailure struct {\n\tRegion   int    `json:"region"`\n\tCategory string `json:"category"`\n\tCode     string `json:"code"`\n\tCause    string `json:"cause"`\n}\n\n'''
        if s.count(store_anchor) != 1:
            raise SystemExit('V66_STORE_ANCHOR_MISSING')
        s = s.replace(store_anchor, region_type + store_anchor, 1)

        old_loop = '''\tfor region := 0; region < 9; region++ {\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "MAP"; j.Region = region + 1 })\n\t\tplayers, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)\n\t\tif err != nil {\n\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_REGION_FAILED")\n\t\t\tfail("MAP_REGION_FAILED", err)\n\t\t\treturn\n\t\t}\n\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n\t\tif err != nil {\n\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_INGEST_FAILED")\n\t\t\tfail("MAP_INGEST_FAILED", err)\n\t\t\treturn\n\t\t}\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.PlayersSeen += accepted })\n\t}\n'''
        new_loop = '''\tfor region := 0; region < 9; region++ {\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "MAP"; j.Region = region + 1 })\n\t\tplayers, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)\n\t\tif err != nil {\n\t\t\td := buildCollectorFailureDiagnosticV65(query, "MAP", region+1, "MAP_REGION_FAILED", err)\n\t\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\t\tj.RegionsFailed++\n\t\t\t\tj.RegionFailures = append(j.RegionFailures, collectorRegionFailure{\n\t\t\t\t\tRegion: region + 1, Category: d.Category, Code: d.Code, Cause: d.Cause,\n\t\t\t\t})\n\t\t\t\tj.FailureCategory = d.Category\n\t\t\t\tj.FailureCode = d.Code\n\t\t\t\tj.FailureCause = d.Cause\n\t\t\t\tj.FailurePhase = d.FailurePhase\n\t\t\t\tj.ServerTarget = d.ServerTarget\n\t\t\t\tj.AuthState = d.AuthState\n\t\t\t})\n\t\t\t// Region isolation V6.6: a protocol-special or temporarily unavailable\n\t\t\t// region must not discard observations from the other eight regions.\n\t\t\tcontinue\n\t\t}\n\t\taccepted, err := collectorIngest(ctx, players, cycle.ID)\n\t\tif err != nil {\n\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_INGEST_FAILED")\n\t\t\tfail("MAP_INGEST_FAILED", err)\n\t\t\treturn\n\t\t}\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.PlayersSeen += accepted\n\t\t\tj.RegionsCompleted++\n\t\t})\n\t}\n\n\tif current, ok := radarCollectorJobs.get(jobID); ok && current.RegionsCompleted == 0 && current.RegionsFailed > 0 {\n\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_ALL_REGIONS_FAILED")\n\t\tfail("MAP_ALL_REGIONS_FAILED", errors.New("ALL_REGION_SCANS_FAILED"))\n\t\treturn\n\t}\n'''
        if s.count(old_loop) != 1:
            raise SystemExit('V66_REGION_LOOP_ANCHOR_MISSING')
        s = s.replace(old_loop, new_loop, 1)
        collector.write_text(s, encoding='utf-8')
        print('RADAR_V66_REGION_ISOLATION=PATCHED')

worker = Path('/tmp/wfgg-radar/src/worker.js')
if worker.is_file():
    s = worker.read_text(encoding='utf-8')
    if '// WFGG_RADAR_REGION_ISOLATION_V66' not in s and 'WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65' in s:
        anchor = "function normalizeFederatedDiagnosticV65(job) {\n"
        helper = '''// WFGG_RADAR_REGION_ISOLATION_V66\nfunction normalizeRegionIsolationV66(job) {\n  if (!job || typeof job !== 'object') return job;\n  const failures = Array.isArray(job.regionFailures) ? job.regionFailures : [];\n  job.regionsFailed = Number(job.regionsFailed || failures.length || 0);\n  job.regionsCompleted = Number(job.regionsCompleted || 0);\n  job.partial = job.status === 'SUCCESS' && job.regionsFailed > 0;\n  return job;\n}\n\n'''
        if s.count(anchor) != 1:
            raise SystemExit('V66_WORKER_HELPER_ANCHOR_MISSING')
        s = s.replace(anchor, helper + anchor, 1)
        status_anchor = '          normalizeFederatedDiagnosticV65(job);\n'
        if s.count(status_anchor) != 1:
            raise SystemExit('V66_WORKER_STATUS_ANCHOR_MISSING')
        s = s.replace(status_anchor, status_anchor + '          normalizeRegionIsolationV66(job);\n', 1)
        worker.write_text(s, encoding='utf-8')
        print('RADAR_V66_WORKER_REGION_ISOLATION=PATCHED')

ui = Path('/tmp/wfgg-radar/public/live-radar.html')
if ui.is_file():
    s = ui.read_text(encoding='utf-8')
    if 'WFGG_RADAR_REGION_ISOLATION_UI_V66' not in s and 'WFGG_RADAR_FEDERATED_DIAGNOSTICS_UI_V65' in s:
        old_success = "else if(job.status==='SUCCESS'){const p=job.player||{};title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]} · TERMINÉ`;meta.textContent=`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} décodés · ${fmt(p.uniqueUIDs||0)} UID uniques · ${fmt(p.accepted||job.enriched||0)} intégrés`}"
        new_success = "else if(job.status==='SUCCESS'){/* WFGG_RADAR_REGION_ISOLATION_UI_V66 */const p=job.player||{};const failed=Number(job.regionsFailed||0)||0;const done=Number(job.regionsCompleted||0)||Math.max(0,(Number(job.regions||9)||9)-failed);const first=Array.isArray(job.regionFailures)&&job.regionFailures.length?job.regionFailures[0]:null;title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]} · ${failed?'TERMINÉ PARTIEL':'TERMINÉ'}`;meta.textContent=failed?`${done}/${job.regions||9} régions OK · ${failed} isolée(s) · première R${first?.region||'?'} ${first?.cause||first?.code||'ERREUR'} · ${fmt(p.decoded||job.playersSeen||0)} décodés`:`${fmt(p.regions||job.regions||0)}/9 régions · ${fmt(p.decoded||job.playersSeen||0)} décodés · ${fmt(p.uniqueUIDs||0)} UID uniques · ${fmt(p.accepted||job.enriched||0)} intégrés`}"
        if s.count(old_success) != 1:
            raise SystemExit('V66_UI_SUCCESS_ANCHOR_MISSING')
        s = s.replace(old_success, new_success, 1)
        old_done = "if(phase==='DONE'||job.status==='SUCCESS'){steps(4);setStatus('CYCLE TERMINÉ','Base Collector actualisée','ok');return}"
        new_done = "if(phase==='DONE'||job.status==='SUCCESS'){steps(4);const rf=Number(job.regionsFailed||0)||0;setStatus(rf?'CYCLE TERMINÉ PARTIEL':'CYCLE TERMINÉ',rf?`${rf} région(s) isolée(s) · données valides conservées`:'Base Collector actualisée','ok');return}"
        if s.count(old_done) != 1:
            raise SystemExit('V66_UI_DONE_ANCHOR_MISSING')
        s = s.replace(old_done, new_done, 1)
        ui.write_text(s, encoding='utf-8')
        print('RADAR_V66_UI_REGION_ISOLATION=PATCHED')

print('RADAR_REGION_ISOLATION_V66=READY')
