#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
DST = ROOT / 'connector-go' / 'cmd' / 'radar-connector'
COLLECTOR = DST / 'collector_jobs.go'
MAIN = DST / 'main.go'
AUTOPILOT = DST / 'server_autopilot_v6194.go'
TRANSPORT = ROOT / 'src' / 'game' / 'remote-transport.js'
WORKER = ROOT / 'src' / 'worker.js'
UI = ROOT / 'public' / 'live-radar.html'
TEST = DST / 'manual_search_stop_v61911_test.go'

# ---------------------------------------------------------------------------
# Connector: cancellable MANUAL Collector jobs.
# ---------------------------------------------------------------------------
text = COLLECTOR.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_MANUAL_SEARCH_STOP_V61911'
if marker not in text:
    request_anchor = '''type collectorSearchRequest struct {
\tToken string `json:"token"`
\tQuery string `json:"query"`
}
'''
    if text.count(request_anchor) != 1:
        raise SystemExit(f'V61911_REQUEST_ANCHOR_COUNT={text.count(request_anchor)}')
    text = text.replace(
        request_anchor,
        request_anchor + '''
type collectorSearchStopRequest struct {
\tID string `json:"id"`
}
''',
        1,
    )

    store_anchor = 'var radarCollectorJobs = &collectorJobStore{jobs: map[string]*collectorJob{}}\n'
    if text.count(store_anchor) != 1:
        raise SystemExit(f'V61911_STORE_ANCHOR_COUNT={text.count(store_anchor)}')
    text = text.replace(
        store_anchor,
        store_anchor + '''
''' + marker + '''
type collectorJobCancelStoreV61911 struct {
\tmu      sync.Mutex
\tcancels map[string]context.CancelFunc
}

var radarCollectorJobCancelsV61911 = &collectorJobCancelStoreV61911{cancels: map[string]context.CancelFunc{}}

func (s *collectorJobCancelStoreV61911) set(id string, cancel context.CancelFunc) {
\ts.mu.Lock()
\tdefer s.mu.Unlock()
\ts.cancels[id] = cancel
}

func (s *collectorJobCancelStoreV61911) remove(id string) {
\ts.mu.Lock()
\tdefer s.mu.Unlock()
\tdelete(s.cancels, id)
}

func (s *collectorJobCancelStoreV61911) cancel(id string) bool {
\ts.mu.Lock()
\tcancel := s.cancels[id]
\ts.mu.Unlock()
\tif cancel == nil {
\t\treturn false
\t}
\tcancel()
\treturn true
}
''',
        1,
    )

    start_anchor = '''\tj := radarCollectorJobs.add(input.Query)
\t// The token is captured only by this goroutine. It is never copied into the
\t// job store, logs, Collector DB, or any persistent VPS file.
\tgo s.runCollectorSearch(j.ID, input.Token, input.Query)
\twriteJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneJob(j)})
'''
    if text.count(start_anchor) != 1:
        raise SystemExit(f'V61911_START_ANCHOR_COUNT={text.count(start_anchor)}')
    text = text.replace(
        start_anchor,
        '''\tj := radarCollectorJobs.add(input.Query)
\t// The token is captured only by this goroutine. It is never copied into the
\t// job store, logs, Collector DB, or any persistent VPS file.
\tparentCtx, parentCancel := context.WithCancel(context.Background())
\tradarCollectorJobCancelsV61911.set(j.ID, parentCancel)
\tgo func() {
\t\tdefer parentCancel()
\t\tdefer radarCollectorJobCancelsV61911.remove(j.ID)
\t\ts.runCollectorSearch(parentCtx, j.ID, input.Token, input.Query)
\t}()
\twriteJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneJob(j)})
''',
        1,
    )

    status_anchor = '''func (s *server) collectorSearchStatus(w http.ResponseWriter, r *http.Request, _ []byte) {
\tid := strings.TrimSpace(r.URL.Query().Get("id"))
\tif id == "" {
\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "JOB_ID_REQUIRED"})
\t\treturn
\t}
\tj, ok := radarCollectorJobs.get(id)
\tif !ok {
\t\twriteJSON(w, http.StatusNotFound, map[string]any{"error": "JOB_NOT_FOUND"})
\t\treturn
\t}
\twriteJSON(w, http.StatusOK, map[string]any{"ok": true, "job": j})
}
'''
    if text.count(status_anchor) != 1:
        raise SystemExit(f'V61911_STATUS_ANCHOR_COUNT={text.count(status_anchor)}')
    stop_handler = status_anchor + '''
func (s *server) collectorSearchStopV61911(w http.ResponseWriter, _ *http.Request, body []byte) {
\tvar input collectorSearchStopRequest
\tif err := decodeJSON(body, &input); err != nil {
\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "COLLECTOR_JOB_ID_REQUIRED"})
\t\treturn
\t}
\tid := strings.TrimSpace(input.ID)
\tif id == "" {
\t\twriteJSON(w, http.StatusBadRequest, map[string]any{"error": "COLLECTOR_JOB_ID_REQUIRED"})
\t\treturn
\t}
\tj, ok := radarCollectorJobs.get(id)
\tif !ok {
\t\twriteJSON(w, http.StatusNotFound, map[string]any{"error": "JOB_NOT_FOUND"})
\t\treturn
\t}
\tif j.Status == "SUCCESS" || j.Status == "FAILED" {
\t\twriteJSON(w, http.StatusOK, map[string]any{"ok": true, "alreadyTerminal": true, "job": j})
\t\treturn
\t}
\tupdated := radarCollectorJobs.update(id, func(job *collectorJob) {
\t\tjob.Phase = "STOPPING"
\t})
\tif !radarCollectorJobCancelsV61911.cancel(id) {
\t\tradarCollectorJobs.update(id, func(job *collectorJob) {
\t\t\tif job.Phase == "STOPPING" {
\t\t\t\tjob.Phase = "RUNNING"
\t\t\t}
\t\t})
\t\twriteJSON(w, http.StatusConflict, map[string]any{"error": "COLLECTOR_JOB_NOT_CANCELLABLE"})
\t\treturn
\t}
\twriteJSON(w, http.StatusAccepted, map[string]any{"ok": true, "stopping": true, "job": updated})
}
'''
    text = text.replace(status_anchor, stop_handler, 1)

    run_anchor = '''func (s *server) runCollectorSearch(jobID, token, query string) {
\tctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)
\tdefer cancel()
'''
    if text.count(run_anchor) != 1:
        raise SystemExit(f'V61911_RUN_ANCHOR_COUNT={text.count(run_anchor)}')
    text = text.replace(
        run_anchor,
        '''func (s *server) runCollectorSearch(parentCtx context.Context, jobID, token, query string) {
\tctx, cancel := context.WithTimeout(parentCtx, 12*time.Minute)
\tdefer cancel()
''',
        1,
    )

    # V6.19.8 owns-cycle terminalization lives inside this fail closure.
    # If STOP cancelled the context, normalize whatever in-flight operation
    # returned into the explicit manual-stop terminal reason.
    cause_anchor = '''\t\tif len(causes) > 0 {
\t\t\tcause = causes[0]
\t\t}
\t\tif ownsCycleV6198 && cycleIDV6198 > 0 {
'''
    if text.count(cause_anchor) != 1:
        raise SystemExit(f'V61911_FAIL_CAUSE_ANCHOR_COUNT={text.count(cause_anchor)}')
    text = text.replace(
        cause_anchor,
        '''\t\tif len(causes) > 0 {
\t\t\tcause = causes[0]
\t\t}
\t\tif current, ok := radarCollectorJobs.get(jobID); ok && current.Phase == "STOPPING" && errors.Is(ctx.Err(), context.Canceled) {
\t\t\tcode = "MANUAL_SEARCH_STOPPED"
\t\t\tcause = ctx.Err()
\t\t}
\t\tif ownsCycleV6198 && cycleIDV6198 > 0 {
''',
        1,
    )

    cycle_start_anchor = '\tcycle, joined, staleRecovered, err := collectorStartCycleWithStaleRecoveryV6197(ctx, query)\n'
    if text.count(cycle_start_anchor) != 1:
        raise SystemExit(f'V61911_CYCLE_START_ANCHOR_COUNT={text.count(cycle_start_anchor)}')
    cancel_helper = '''\tmanualStopIfCancelledV61911 := func() bool {
\t\tif !errors.Is(ctx.Err(), context.Canceled) {
\t\t\treturn false
\t\t}
\t\tfail("MANUAL_SEARCH_STOPPED", ctx.Err())
\t\treturn true
\t}
\tif manualStopIfCancelledV61911() { return }

'''
    text = text.replace(cycle_start_anchor, cancel_helper + cycle_start_anchor, 1)

    loop_anchor = '\tfor region := 0; region < 9; region++ {\n'
    if text.count(loop_anchor) != 1:
        raise SystemExit(f'V61911_MAP_LOOP_ANCHOR_COUNT={text.count(loop_anchor)}')
    text = text.replace(
        loop_anchor,
        loop_anchor + '\t\tif manualStopIfCancelledV61911() { return }\n',
        1,
    )

    finalizing_anchor = '\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })\n'
    if text.count(finalizing_anchor) != 1:
        raise SystemExit(f'V61911_FINALIZING_ANCHOR_COUNT={text.count(finalizing_anchor)}')
    text = text.replace(
        finalizing_anchor,
        '\tif manualStopIfCancelledV61911() { return }\n\n' + finalizing_anchor,
        1,
    )

COLLECTOR.write_text(text, encoding='utf-8')

# Autopilot child cycles keep their existing independent 12-minute lifetime.
autopilot_text = AUTOPILOT.read_text(encoding='utf-8')
autopilot_old = 's.runCollectorSearch(child.ID, token, command)'
autopilot_new = 's.runCollectorSearch(context.Background(), child.ID, token, command)'
if autopilot_old in autopilot_text:
    if autopilot_text.count(autopilot_old) != 1:
        raise SystemExit(f'V61911_AUTOPILOT_CALL_ANCHOR_COUNT={autopilot_text.count(autopilot_old)}')
    autopilot_text = autopilot_text.replace(autopilot_old, autopilot_new, 1)
elif autopilot_new not in autopilot_text:
    raise SystemExit('V61911_AUTOPILOT_CALL_MISSING')
AUTOPILOT.write_text(autopilot_text, encoding='utf-8')

# Connector route.
main_text = MAIN.read_text(encoding='utf-8')
route = 'mux.HandleFunc("POST /v1/collector/search/stop", s.signed(s.collectorSearchStopV61911))'
if route not in main_text:
    anchor = 'mux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))'
    if main_text.count(anchor) != 1:
        raise SystemExit(f'V61911_MAIN_ROUTE_ANCHOR_COUNT={main_text.count(anchor)}')
    main_text = main_text.replace(anchor, anchor + '\n\t' + route, 1)
MAIN.write_text(main_text, encoding='utf-8')

# ---------------------------------------------------------------------------
# Worker transport.
# ---------------------------------------------------------------------------
transport = TRANSPORT.read_text(encoding='utf-8')
transport_marker = 'WFGG_RADAR_MANUAL_SEARCH_STOP_TRANSPORT_V61911'
if transport_marker not in transport:
    anchor = "  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: 'GET' }); }"
    if transport.count(anchor) != 1:
        raise SystemExit(f'V61911_TRANSPORT_ANCHOR_COUNT={transport.count(anchor)}')
    transport = transport.replace(
        anchor,
        anchor + '''
  // WFGG_RADAR_MANUAL_SEARCH_STOP_TRANSPORT_V61911
  stopCollectorSearch(id) {
    return this.request('/v1/collector/search/stop', { body: { id } });
  }''',
        1,
    )
TRANSPORT.write_text(transport, encoding='utf-8')

# ---------------------------------------------------------------------------
# Cloudflare Worker route. Stopping never reads the Last War credential.
# ---------------------------------------------------------------------------
worker = WORKER.read_text(encoding='utf-8')
worker_marker = 'WFGG_RADAR_MANUAL_SEARCH_STOP_WORKER_V61911'
if worker_marker not in worker:
    anchor = "      if (url.pathname === '/api/radar/search' && request.method === 'GET') {"
    if worker.count(anchor) != 1:
        raise SystemExit(f'V61911_WORKER_ROUTE_ANCHOR_COUNT={worker.count(anchor)}')
    block = r'''      // WFGG_RADAR_MANUAL_SEARCH_STOP_WORKER_V61911
      if (url.pathname === '/api/radar/search/stop' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const body = await bodyJson(request);
        const id = String(body.id || '').trim();
        if (!/^[a-zA-Z0-9_-]{8,128}$/.test(id)) throw Object.assign(new Error('COLLECTOR_JOB_ID_REQUIRED'), { status: 400 });
        const transport = new RemoteLastWarTransport({
          baseUrl: env.RADAR_CONNECTOR_URL,
          sharedKey: env.RADAR_CONNECTOR_SHARED_KEY,
          timeoutMs: 30000
        });
        try {
          const stopped = await transport.stopCollectorSearch(id);
          await audit(env, session.gameUid, 'radar.collector-search.stop', id, {
            jobId: id,
            manual: true,
            gameMutation: false
          });
          return json({ ...stopped, gameReadonly: true, gameMutation: false }, stopped?.alreadyTerminal ? 200 : 202);
        } finally {
          await transport.close().catch(() => {});
        }
      }

'''
    worker = worker.replace(anchor, block + anchor, 1)
WORKER.write_text(worker, encoding='utf-8')

# ---------------------------------------------------------------------------
# UI: same button toggles RECHERCHER -> STOP -> RECHERCHER.
# ---------------------------------------------------------------------------
ui = UI.read_text(encoding='utf-8')
ui_marker = 'WFGG_RADAR_MANUAL_SEARCH_STOP_UI_V61911'
if ui_marker not in ui:
    css_anchor = '.go:disabled{filter:grayscale(.8);opacity:.55}'
    if ui.count(css_anchor) != 1:
        raise SystemExit(f'V61911_UI_CSS_ANCHOR_COUNT={ui.count(css_anchor)}')
    ui = ui.replace(
        css_anchor,
        css_anchor + '.go.stop{background:linear-gradient(#e58671,#983d32);border-color:#d88b78;color:#fff3ee;box-shadow:inset 0 1px #fff5,0 5px 0 #52251f,0 8px 16px #0008}',
        1,
    )

    state_anchor = "const $=id=>document.getElementById(id);const screen=$('screen'),go=$('go'),result=$('result'),login=$('login'),target=$('target');let phaseTimer=null,audioCtx=null;"
    if ui.count(state_anchor) != 1:
        raise SystemExit(f'V61911_UI_STATE_ANCHOR_COUNT={ui.count(state_anchor)}')
    state = state_anchor + """
/* WFGG_RADAR_MANUAL_SEARCH_STOP_UI_V61911 */
let manualSearchRunning=false,manualSearchStopping=false,manualSearchStopPending=false,manualSearchJobId='',manualSearchFederated=false,manualSearchAbortController=null;
function setManualSearchButton(running=false,stopping=false){manualSearchRunning=Boolean(running);manualSearchStopping=Boolean(stopping);go.classList.toggle('stop',manualSearchRunning);go.disabled=manualSearchStopping;go.textContent=manualSearchRunning?(manualSearchStopping?'ARRÊT…':'STOP'):'RECHERCHER'}
async function requestManualSearchStop(){
  if(!manualSearchRunning||manualSearchStopping)return true;
  manualSearchStopPending=true;
  if(!manualSearchFederated){
    manualSearchStopping=true;setManualSearchButton(true,true);setStatus('ARRÊT DU RADAR','Interruption de la recherche manuelle…');
    try{manualSearchAbortController?.abort()}catch(_){}
    return true;
  }
  if(!manualSearchJobId){setStatus('ARRÊT DEMANDÉ','Initialisation du cycle en cours…');return true}
  manualSearchStopping=true;setManualSearchButton(true,true);setStatus('ARRÊT DU RADAR','Interruption de la recherche manuelle…');
  try{await api('/api/radar/search/stop',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id:manualSearchJobId})});return true}
  catch(err){manualSearchStopping=false;manualSearchStopPending=false;setManualSearchButton(true,false);setStatus('ARRÊT IMPOSSIBLE',String(err.message||err),'error');return false}
}
"""
    ui = ui.replace(state_anchor, state, 1)

    start_fn = 'function startScan(q){'
    stop_fn = 'function stopScan(){'
    start_pos = ui.find(start_fn)
    stop_pos = ui.find(stop_fn, start_pos + len(start_fn))
    if start_pos < 0 or stop_pos < 0:
        raise SystemExit('V61911_UI_SCAN_FUNCTIONS_MISSING')
    start_segment = ui[start_pos:stop_pos]
    disable_anchor = 'go.disabled=true;'
    if start_segment.count(disable_anchor) != 1:
        raise SystemExit(f'V61911_UI_START_DISABLE_COUNT={start_segment.count(disable_anchor)}')
    start_segment = start_segment.replace(
        disable_anchor,
        "manualSearchJobId='';manualSearchStopPending=false;manualSearchFederated=/^@federated:(?:APS)?\\d+/i.test(q);manualSearchAbortController=manualSearchFederated?null:new AbortController();setManualSearchButton(true,false);",
        1,
    )
    ui = ui[:start_pos] + start_segment + ui[stop_pos:]

    # Replace only the legacy enable action inside stopScan, preserving the rest.
    stop_pos = ui.find(stop_fn)
    sleep_pos = ui.find('function sleep(ms)', stop_pos)
    if stop_pos < 0 or sleep_pos < 0:
        raise SystemExit('V61911_UI_STOPSCAN_RANGE_MISSING')
    stop_segment = ui[stop_pos:sleep_pos]
    enable_anchor = 'go.disabled=false'
    if stop_segment.count(enable_anchor) != 1:
        raise SystemExit(f'V61911_UI_STOP_ENABLE_COUNT={stop_segment.count(enable_anchor)}')
    stop_segment = stop_segment.replace(
        enable_anchor,
        "manualSearchJobId='';manualSearchStopPending=false;manualSearchFederated=false;manualSearchAbortController=null;setManualSearchButton(false,false)",
        1,
    )
    ui = ui[:stop_pos] + stop_segment + ui[sleep_pos:]

    # A local indexed search is abortable too, even though it normally finishes fast.
    api_anchor = "const r=await fetch(path,{credentials:'include',cache:'no-store',...opt});"
    if ui.count(api_anchor) != 1:
        raise SystemExit(f'V61911_UI_API_ANCHOR_COUNT={ui.count(api_anchor)}')
    ui = ui.replace(
        api_anchor,
        "const manualOpt=(manualSearchRunning&&!manualSearchFederated&&String(path).startsWith('/api/radar/search?')&&manualSearchAbortController)?{signal:manualSearchAbortController.signal}:{};const r=await fetch(path,{credentials:'include',cache:'no-store',...manualOpt,...opt});",
        1,
    )

    # Once a Collector job id exists, STOP targets exactly that job.
    run_start = 'async function runCollectorSearch(q){'
    run_end = 'function pick('
    rs = ui.find(run_start)
    re = ui.find(run_end, rs + len(run_start))
    if rs < 0 or re < 0:
        raise SystemExit('V61911_UI_RUN_RANGE_MISSING')
    run_segment = ui[rs:re]
    load_anchor = 'let job=await loadOrStartCollectorJob(q);'
    poll_anchor = 'job=await fetchCollectorJobResilient(job.id,job);'
    if run_segment.count(load_anchor) != 1 or run_segment.count(poll_anchor) != 1:
        raise SystemExit(f'V61911_UI_RUN_ANCHORS={run_segment.count(load_anchor)}/{run_segment.count(poll_anchor)}')
    run_segment = run_segment.replace(
        load_anchor,
        load_anchor + "manualSearchJobId=String(job.id||'');if(manualSearchStopPending)await requestManualSearchStop();",
        1,
    )
    run_segment = run_segment.replace(
        poll_anchor,
        poll_anchor + "manualSearchJobId=String(job.id||manualSearchJobId);",
        1,
    )
    ui = ui[:rs] + run_segment + ui[re:]

    submit_anchor = "$('searchForm').onsubmit=async e=>{e.preventDefault();"
    if ui.count(submit_anchor) != 1:
        raise SystemExit(f'V61911_UI_SUBMIT_ANCHOR_COUNT={ui.count(submit_anchor)}')
    ui = ui.replace(
        submit_anchor,
        submit_anchor + "if(manualSearchRunning){await requestManualSearchStop();return}",
        1,
    )

    catch_anchor = "}catch(err){stopScan();screen.classList.remove('found');if(err.status===401){"
    if ui.count(catch_anchor) != 1:
        raise SystemExit(f'V61911_UI_CATCH_ANCHOR_COUNT={ui.count(catch_anchor)}')
    ui = ui.replace(
        catch_anchor,
        "}catch(err){const manualStopped=err?.name==='AbortError'||String(err?.message||'')==='MANUAL_SEARCH_STOPPED';stopScan();screen.classList.remove('found');if(manualStopped){steps(0);setStatus('RADAR ARRÊTÉ','Recherche manuelle interrompue','ok');$('federatedTitle').textContent='COLLECTOR FÉDÉRÉ · ARRÊTÉ';$('federatedMeta').textContent='Recherche manuelle interrompue par l’utilisateur.';tone(300,.06,.018)}else if(err.status===401){",
        1,
    )

UI.write_text(ui, encoding='utf-8')

# ---------------------------------------------------------------------------
# Connector tests.
# ---------------------------------------------------------------------------
TEST.write_text(r'''package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func isolateManualStopStoresV61911(t *testing.T) {
	t.Helper()
	oldJobs := radarCollectorJobs
	oldCancels := radarCollectorJobCancelsV61911
	radarCollectorJobs = &collectorJobStore{jobs: map[string]*collectorJob{}}
	radarCollectorJobCancelsV61911 = &collectorJobCancelStoreV61911{cancels: map[string]context.CancelFunc{}}
	t.Cleanup(func() {
		radarCollectorJobs = oldJobs
		radarCollectorJobCancelsV61911 = oldCancels
	})
}

func TestCollectorSearchStopV61911CancelsActiveJob(t *testing.T) {
	isolateManualStopStoresV61911(t)
	j := radarCollectorJobs.add("@federated:8120")
	radarCollectorJobs.update(j.ID, func(x *collectorJob) {
		x.Status = "RUNNING"
		x.Phase = "MAP"
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	radarCollectorJobCancelsV61911.set(j.ID, cancel)

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/collector/search/stop", nil)
	body := []byte("{\"id\":\"" + j.ID + "\"}")
	(&server{}).collectorSearchStopV61911(rr, req, body)

	if rr.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	select {
	case <-ctx.Done():
	default:
		t.Fatal("expected manual stop to cancel the job context")
	}
	got, ok := radarCollectorJobs.get(j.ID)
	if !ok || got.Phase != "STOPPING" {
		t.Fatalf("job not marked STOPPING: %#v", got)
	}
}

func TestCollectorSearchStopV61911LeavesTerminalJobAlone(t *testing.T) {
	isolateManualStopStoresV61911(t)
	j := radarCollectorJobs.add("Player")
	radarCollectorJobs.update(j.ID, func(x *collectorJob) {
		x.Status = "SUCCESS"
		x.Phase = "DONE"
		x.FinishedAt = utcNow()
	})

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/collector/search/stop", nil)
	body := []byte("{\"id\":\"" + j.ID + "\"}")
	(&server{}).collectorSearchStopV61911(rr, req, body)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	got, _ := radarCollectorJobs.get(j.ID)
	if got.Status != "SUCCESS" || got.Phase != "DONE" {
		t.Fatalf("terminal job changed: %#v", got)
	}
}
''', encoding='utf-8')

print('RADAR_V61911_MANUAL_SEARCH_STOP=READY')
