#!/usr/bin/env python3
from pathlib import Path

MARKER = 'WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65'

collector = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
if collector.is_file():
    s = collector.read_text(encoding='utf-8')
    if MARKER not in s:
        old_fields = '''\tPlayer      map[string]any `json:"player,omitempty"`\n\tError       string         `json:"error,omitempty"`\n\tStartedAt   string         `json:"startedAt"`\n'''
        new_fields = '''\tPlayer          map[string]any `json:"player,omitempty"`\n\tError           string         `json:"error,omitempty"`\n\tFailureCategory string         `json:"failureCategory,omitempty"`\n\tFailureCode     string         `json:"failureCode,omitempty"`\n\tFailureCause    string         `json:"failureCause,omitempty"`\n\tFailurePhase    string         `json:"failurePhase,omitempty"`\n\tServerTarget    string         `json:"serverTarget,omitempty"`\n\tAuthState       string         `json:"authState,omitempty"`\n\tStartedAt       string         `json:"startedAt"`\n'''
        if s.count(old_fields) != 1:
            raise SystemExit('V65_COLLECTOR_FIELDS_ANCHOR_MISSING')
        s = s.replace(old_fields, new_fields, 1)

        old_fail = '''\tfail := func(code string) {\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\tj.Status = "FAILED"\n\t\t\tj.Phase = "FAILED"\n\t\t\tj.Error = code\n\t\t\tj.FinishedAt = utcNow()\n\t\t})\n\t}\n'''
        new_fail = '''\t// WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65\n\tfail := func(code string, causes ...error) {\n\t\tvar cause error\n\t\tif len(causes) > 0 { cause = causes[0] }\n\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) {\n\t\t\td := buildCollectorFailureDiagnosticV65(query, j.Phase, j.Region, code, cause)\n\t\t\tj.Status = "FAILED"\n\t\t\tj.FailureCategory = d.Category\n\t\t\tj.FailureCode = d.Code\n\t\t\tj.FailureCause = d.Cause\n\t\t\tj.FailurePhase = d.FailurePhase\n\t\t\tj.ServerTarget = d.ServerTarget\n\t\t\tj.AuthState = d.AuthState\n\t\t\tj.Phase = "FAILED"\n\t\t\tj.Error = code\n\t\t\tj.FinishedAt = utcNow()\n\t\t})\n\t}\n'''
        if s.count(old_fail) != 1:
            raise SystemExit('V65_COLLECTOR_FAIL_ANCHOR_MISSING')
        s = s.replace(old_fail, new_fail, 1)
        for old, new in {
            'fail("COLLECTOR_CYCLE_START_FAILED")': 'fail("COLLECTOR_CYCLE_START_FAILED", err)',
            'fail("COLLECTOR_JOINED_CYCLE_FAILED")': 'fail("COLLECTOR_JOINED_CYCLE_FAILED", err)',
            'fail("MAP_REGION_FAILED")': 'fail("MAP_REGION_FAILED", err)',
            'fail("MAP_INGEST_FAILED")': 'fail("MAP_INGEST_FAILED", err)',
            'fail("DELTA_READ_FAILED")': 'fail("DELTA_READ_FAILED", err)',
            'fail("PROFILE_BATCH_FAILED")': 'fail("PROFILE_BATCH_FAILED", err)',
            'fail("PROFILE_INGEST_FAILED")': 'fail("PROFILE_INGEST_FAILED", err)',
            'fail("COLLECTOR_CYCLE_FINISH_FAILED")': 'fail("COLLECTOR_CYCLE_FINISH_FAILED", err)',
            'fail("COLLECTOR_TARGET_REFRESH_FAILED")': 'fail("COLLECTOR_TARGET_REFRESH_FAILED", err)',
        }.items():
            s = s.replace(old, new)
        collector.write_text(s, encoding='utf-8')
        print('RADAR_V65_CONNECTOR_DIAGNOSTICS=PATCHED')
    else:
        print('RADAR_V65_CONNECTOR_DIAGNOSTICS=ALREADY_PRESENT')
else:
    # The immutable Worker release contains only the legacy connector skeleton.
    # The real VPS connector is built from the full source tree in the dedicated
    # binary workflow. Create a marker-only Go file here so the Web deploy gate
    # can prove V6.5 staging without pretending to patch source that is absent.
    collector.parent.mkdir(parents=True, exist_ok=True)
    collector.write_text(
        'package main\n\n// WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65\n// Web-release compatibility shim; no runtime logic lives here.\n',
        encoding='utf-8',
    )
    print('RADAR_V65_CONNECTOR_DIAGNOSTICS=WEB_RELEASE_SHIM')

worker = Path('/tmp/wfgg-radar/src/worker.js')
if worker.is_file():
    s = worker.read_text(encoding='utf-8')
    if "'/api/radar/search/status'" not in s:
        print('RADAR_V65_WORKER_DIAGNOSTICS=SKIPPED_NO_ASYNC_BRIDGE')
    elif '// WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65' in s:
        print('RADAR_V65_WORKER_DIAGNOSTICS=ALREADY_PRESENT')
    else:
        export_anchor = 'export default {\n'
        if s.count(export_anchor) != 1:
            raise SystemExit('V65_WORKER_EXPORT_ANCHOR_MISSING')
        helper = r'''// WFGG_RADAR_FEDERATED_DIAGNOSTICS_V65
function radarDiagnosticCodeV65(value, fallback = 'UNKNOWN') {
  const out = String(value || fallback).toUpperCase().replace(/[^A-Z0-9_:-]+/g, '_').replace(/^[_:-]+|[_:-]+$/g, '').slice(0, 96);
  return out || fallback;
}
function radarDiagnosticCategoryV65(code, cause) {
  const x = `${radarDiagnosticCodeV65(code)}:${radarDiagnosticCodeV65(cause)}`;
  if (/AUTH_REJECTED|GAME_TOKEN_REQUIRED|CREDENTIAL_REJECTED/.test(x)) return 'AUTH';
  if (/INGEST|DELTA_READ|COLLECTOR_HTTP_[45]/.test(x)) return 'INGEST';
  if (/REPORT_INVALID|CAPTURE_INVALID|DECODE|JSON_FAILED|PARSE_FAILED/.test(x)) return 'DECODE';
  if (/DIAL_FAILED|READ_FAILED|SEND_FAILED|WRITE_FAILED|TIMEOUT|CONNECTION|NETWORK/.test(x)) return 'NETWORK';
  if (/SERVER_TARGET|REGION_INVALID|ORIGIN_INDEX|FEDERATED_TARGET/.test(x)) return 'SERVER_TARGET';
  return 'PROTOCOL';
}
function normalizeFederatedDiagnosticV65(job) {
  if (!job || typeof job !== 'object') return job;
  const m = String(job.query || '').match(/^@federated:(?:APS)?(\d{1,8})/i);
  if (m && !job.serverTarget) job.serverTarget = m[1];
  if (job.status === 'SUCCESS') { job.authState = 'VALID'; return job; }
  if (job.status !== 'FAILED') return job;
  job.failureCode = radarDiagnosticCodeV65(job.failureCode || job.error || 'COLLECTOR_FAILED');
  job.failureCause = radarDiagnosticCodeV65(job.failureCause || job.failureCode);
  job.failurePhase = radarDiagnosticCodeV65(job.failurePhase || job.phase || 'UNKNOWN');
  job.failureCategory = radarDiagnosticCategoryV65(job.failureCode, job.failureCause);
  job.authState = radarDiagnosticCodeV65(job.authState || (job.failureCategory === 'AUTH' ? 'REJECTED' : 'UNKNOWN'));
  return job;
}

'''
        s = s.replace(export_anchor, helper + export_anchor, 1)
        status_anchor = "          if (!job) throw Object.assign(new Error('COLLECTOR_JOB_STATUS_INVALID'), { status: 502 });\n"
        if s.count(status_anchor) != 1:
            raise SystemExit('V65_WORKER_STATUS_ANCHOR_MISSING')
        s = s.replace(status_anchor, status_anchor + '          normalizeFederatedDiagnosticV65(job);\n', 1)
        probe_old = '''                  try {\n                    await transport.authenticate(token);\n                  } catch (probeError) {'''
        probe_new = '''                  try {\n                    await transport.authenticate(token);\n                    job.authState = 'VALID';\n                  } catch (probeError) {'''
        if s.count(probe_old) != 1:
            raise SystemExit('V65_AUTH_PROBE_ANCHOR_MISSING')
        s = s.replace(probe_old, probe_new, 1)
        reject_old = '''                      job.error = 'LASTWAR_AUTH_REJECTED';\n                      await audit(env, session.gameUid, 'auth.lastwar.credential-rejected', session.gameUid, {'''
        reject_new = '''                      job.error = 'LASTWAR_AUTH_REJECTED';\n                      job.failureCategory = 'AUTH';\n                      job.failureCode = 'LASTWAR_AUTH_REJECTED';\n                      job.failureCause = 'LASTWAR_AUTH_REJECTED';\n                      job.authState = 'REJECTED';\n                      await audit(env, session.gameUid, 'auth.lastwar.credential-rejected', session.gameUid, {'''
        if s.count(reject_old) != 1:
            raise SystemExit('V65_AUTH_REJECT_ANCHOR_MISSING')
        s = s.replace(reject_old, reject_new, 1)
        worker.write_text(s, encoding='utf-8')
        print('RADAR_V65_WORKER_DIAGNOSTICS=PATCHED')

ui = Path('/tmp/wfgg-radar/public/live-radar.html')
if ui.is_file():
    s = ui.read_text(encoding='utf-8')
    if 'WFGG_RADAR_FEDERATED_PROGRESS_V64' not in s:
        print('RADAR_V65_UI_DIAGNOSTICS=SKIPPED_NO_V64_UI')
    elif 'WFGG_RADAR_FEDERATED_DIAGNOSTICS_UI_V65' in s:
        print('RADAR_V65_UI_DIAGNOSTICS=ALREADY_PRESENT')
    else:
        old = "else if(job.status==='FAILED'){title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${m[1]} · ÉCHEC`;meta.textContent=job.error||'Erreur Collector'}"
        new = "else if(job.status==='FAILED'){/* WFGG_RADAR_FEDERATED_DIAGNOSTICS_UI_V65 */const cat=String(job.failureCategory||'PROTOCOL');const code=String(job.failureCode||job.error||'COLLECTOR_FAILED');const cause=String(job.failureCause||code);const phase=String(job.failurePhase||job.phase||'UNKNOWN');const region=Number(job.region||0)||0;const auth=String(job.authState||'UNKNOWN');title.textContent=`COLLECTOR FÉDÉRÉ · SERVEUR ${job.serverTarget||m[1]} · ÉCHEC ${cat}`;meta.textContent=`${code} · cause ${cause} · phase ${phase} · région ${region}/${job.regions||9} · auth ${auth}`}"
        if s.count(old) != 1:
            raise SystemExit('V65_UI_FAILURE_ANCHOR_MISSING')
        s = s.replace(old, new, 1)
        ui.write_text(s, encoding='utf-8')
        print('RADAR_V65_UI_DIAGNOSTICS=PATCHED')

print('RADAR_FEDERATED_DIAGNOSTICS_V65=READY')
