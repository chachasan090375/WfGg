#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
COLLECTOR = ROOT / 'connector-go' / 'cmd' / 'radar-connector' / 'collector_jobs.go'
MAIN = ROOT / 'connector-go' / 'cmd' / 'radar-connector' / 'main.go'
TRANSPORT = ROOT / 'src' / 'game' / 'remote-transport.js'
WORKER = ROOT / 'src' / 'worker.js'
UI = ROOT / 'public' / 'live-radar.html'
TEST = ROOT / 'connector-go' / 'cmd' / 'radar-connector' / 'manual_search_stop_v61911_test.go'

# ---------------------------------------------------------------------------
# Connector: cancellable MANUAL Collector jobs only.
# ---------------------------------------------------------------------------
text = COLLECTOR.read_text(encoding='utf-8')
marker = '// WFGG_RADAR_MANUAL_SEARCH_STOP_V61911'
if marker not in text:
    req_anchor = '''type collectorSearchRequest struct {
	Token string `json:"token"`
	Query string `json:"query"`
}
'''
    if text.count(req_anchor) != 1:
        raise SystemExit(f'V61911_REQUEST_ANCHOR_COUNT={text.count(req_anchor)}')
    req_repl = req_anchor + '''
type collectorSearchStopRequest struct {
	ID string `json:"id"`
}
'''
    text = text.replace(req_anchor, req_repl, 1)

    store_anchor = 'var radarCollectorJobs = &collectorJobStore{jobs: map[string]*collectorJob{}}\n'
    if text.count(store_anchor) != 1:
        raise SystemExit(f'V61911_STORE_ANCHOR_COUNT={text.count(store_anchor)}')
    store_repl = store_anchor + '''
''' + marker + '''
type collectorJobCancelStoreV61911 struct {
	mu      sync.Mutex
	cancels map[string]context.CancelFunc
}

var radarCollectorJobCancelsV61911 = &collectorJobCancelStoreV61911{cancels: map[string]context.CancelFunc{}}

func (s *collectorJobCancelStoreV61911) set(id string, cancel context.CancelFunc) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cancels[id] = cancel
}

func (s *collectorJobCancelStoreV61911) remove(id string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.cancels, id)
}

func (s *collectorJobCancelStoreV61911) cancel(id string) bool {
	s.mu.Lock()
	cancel := s.cancels[id]
	s.mu.Unlock()
	if cancel == nil {
		return false
	}
	cancel()
	return true
}
'''
    text = text.replace(store_anchor, store_repl, 1)

    start_anchor = '''	j := radarCollectorJobs.add(input.Query)
	// The token is captured only by this goroutine. It is never copied into the
	// job store, logs, Collector DB, or any persistent VPS file.
	go s.runCollectorSearch(j.ID, input.Token, input.Query)
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneJob(j)})
'''
    if text.count(start_anchor) != 1:
        raise SystemExit(f'V61911_START_ANCHOR_COUNT={text.count(start_anchor)}')
    start_repl = '''	j := radarCollectorJobs.add(input.Query)
	// The token is captured only by this goroutine. It is never copied into the
	// job store, logs, Collector DB, or any persistent VPS file.
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)
	radarCollectorJobCancelsV61911.set(j.ID, cancel)
	go func() {
		defer cancel()
		defer radarCollectorJobCancelsV61911.remove(j.ID)
		s.runCollectorSearch(ctx, j.ID, input.Token, input.Query)
	}()
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "job": cloneJob(j)})
'''
    text = text.replace(start_anchor, start_repl, 1)

    status_anchor = '''func (s *server) collectorSearchStatus(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.TrimSpace(r.URL.Query().Get("id"))
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "JOB_ID_REQUIRED"})
		return
	}
	j, ok := radarCollectorJobs.get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "JOB_NOT_FOUND"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "job": j})
}
'''
    if text.count(status_anchor) != 1:
        raise SystemExit(f'V61911_STATUS_ANCHOR_COUNT={text.count(status_anchor)}')
    stop_handler = status_anchor + '''
func (s *server) collectorSearchStopV61911(w http.ResponseWriter, _ *http.Request, body []byte) {
	var input collectorSearchStopRequest
	if err := decodeJSON(body, &input); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "COLLECTOR_JOB_ID_REQUIRED"})
		return
	}
	id := strings.TrimSpace(input.ID)
	if id == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "COLLECTOR_JOB_ID_REQUIRED"})
		return
	}
	j, ok := radarCollectorJobs.get(id)
	if !ok {
		writeJSON(w, http.StatusNotFound, map[string]any{"error": "JOB_NOT_FOUND"})
		return
	}
	if j.Status == "SUCCESS" || j.Status == "FAILED" {
		writeJSON(w, http.StatusOK, map[string]any{"ok": true, "alreadyTerminal": true, "job": j})
		return
	}
	radarCollectorJobs.update(id, func(job *collectorJob) {
		job.Phase = "STOPPING"
	})
	if !radarCollectorJobCancelsV61911.cancel(id) {
		writeJSON(w, http.StatusConflict, map[string]any{"error": "COLLECTOR_JOB_NOT_CANCELLABLE"})
		return
	}
	updated, _ := radarCollectorJobs.get(id)
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "stopping": true, "job": updated})
}
'''
    text = text.replace(status_anchor, stop_handler, 1)

    run_anchor = '''func (s *server) runCollectorSearch(jobID, token, query string) {
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)
	defer cancel()
'''
    if text.count(run_anchor) != 1:
        raise SystemExit(f'V61911_RUN_ANCHOR_COUNT={text.count(run_anchor)}')
    text = text.replace(run_anchor, 'func (s *server) runCollectorSearch(ctx context.Context, jobID, token, query string) {\n', 1)

    run_func_pos = text.index('func (s *server) runCollectorSearch(ctx context.Context, jobID, token, query string) {')
    running_status = 'j.Status = "RUNNING"'
    running_status_pos = text.find(running_status, run_func_pos)
    if running_status_pos < 0:
        raise SystemExit('V61911_RUNNING_STATUS_ANCHOR_MISSING')
    running_stmt_pos = text.rfind('radarCollectorJobs.update(jobID', run_func_pos, running_status_pos)
    if running_stmt_pos < 0:
        raise SystemExit('V61911_RUNNING_UPDATE_ANCHOR_MISSING')
    running_line_start = text.rfind('\n', run_func_pos, running_stmt_pos) + 1
    cancel_helper = '''\tmanualStopIfCancelledV61911 := func() bool {
\t\tif !errors.Is(ctx.Err(), context.Canceled) {
\t\t\treturn false
\t\t}
\t\tfail("MANUAL_SEARCH_STOPPED", ctx.Err())
\t\treturn true
\t}
\tif manualStopIfCancelledV61911() {
\t\treturn
\t}

'''
    text = text[:running_line_start] + cancel_helper + text[running_line_start:]

    replacements = [
        (
'''\tcycle, joined, staleRecovered, err := collectorStartCycleWithStaleRecoveryV6197(ctx, query)
\tif staleRecovered {
\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "STALE_CYCLE_RECOVERED" })
\t}
\tif err != nil {
\t\tfail("COLLECTOR_CYCLE_START_FAILED", err)
''',
'''\tcycle, joined, staleRecovered, err := collectorStartCycleWithStaleRecoveryV6197(ctx, query)
\tif staleRecovered {
\t\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "STALE_CYCLE_RECOVERED" })
\t}
\tif err != nil {
\t\tif manualStopIfCancelledV61911() { return }
\t\tfail("COLLECTOR_CYCLE_START_FAILED", err)
'''
        ),
        (
'''		if err := waitCollectorCycle(ctx, cycle.ID); err != nil {
			fail("COLLECTOR_JOINED_CYCLE_FAILED", err)
''',
'''		if err := waitCollectorCycle(ctx, cycle.ID); err != nil {
			if manualStopIfCancelledV61911() { return }
			fail("COLLECTOR_JOINED_CYCLE_FAILED", err)
'''
        ),
        (
'''		players, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)
		if err != nil {
''',
'''		players, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)
		if err != nil {
			if manualStopIfCancelledV61911() { return }
'''
        ),
        (
'''		accepted, err := collectorIngest(ctx, players, cycle.ID)
		if err != nil {
''',
'''		accepted, err := collectorIngest(ctx, players, cycle.ID)
		if err != nil {
			if manualStopIfCancelledV61911() { return }
'''
        ),
        (
'''	uids, err := collectorChangedUIDs(ctx, cycle.ID)
	if err != nil {
''',
'''	uids, err := collectorChangedUIDs(ctx, cycle.ID)
	if err != nil {
		if manualStopIfCancelledV61911() { return }
'''
        ),
        (
'''			players, err := profileScanner.ScanProfiles(ctx, token, uids[start:end])
			if err != nil {
''',
'''			players, err := profileScanner.ScanProfiles(ctx, token, uids[start:end])
			if err != nil {
				if manualStopIfCancelledV61911() { return }
'''
        ),
        (
'''			accepted, err := collectorIngest(ctx, players, cycle.ID)
			if err != nil {
''',
'''			accepted, err := collectorIngest(ctx, players, cycle.ID)
			if err != nil {
				if manualStopIfCancelledV61911() { return }
'''
        ),
        (
'''	_ = s.refreshSearchTarget(ctx, token, query, cycle.ID, jobID)

	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })
''',
'''	_ = s.refreshSearchTarget(ctx, token, query, cycle.ID, jobID)
	if manualStopIfCancelledV61911() { return }

	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "FINALIZING" })
'''
        ),
        (
'''	if err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {
		fail("COLLECTOR_CYCLE_FINISH_FAILED", err)
''',
'''	if err := collectorFinishCycle(ctx, cycle.ID, "SUCCESS", ""); err != nil {
		if manualStopIfCancelledV61911() { return }
		fail("COLLECTOR_CYCLE_FINISH_FAILED", err)
'''
        ),
    ]
    for old, new in replacements:
        if text.count(old) != 1:
            raise SystemExit(f'V61911_CANCEL_CHECK_ANCHOR_COUNT={text.count(old)} TEXT={old[:70]!r}')
        text = text.replace(old, new, 1)

COLLECTOR.write_text(text, encoding='utf-8')

# ---------------------------------------------------------------------------
# Connector route.
# ---------------------------------------------------------------------------
text = MAIN.read_text(encoding='utf-8')
if 'collectorSearchStopV61911' not in text:
    anchor = 'mux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))'
    if text.count(anchor) != 1:
        raise SystemExit(f'V61911_MAIN_ROUTE_ANCHOR_COUNT={text.count(anchor)}')
    text = text.replace(
        anchor,
        anchor + '\n\tmux.HandleFunc("POST /v1/collector/search/stop", s.signed(s.collectorSearchStopV61911))',
        1,
    )
MAIN.write_text(text, encoding='utf-8')

# ---------------------------------------------------------------------------
# Worker transport.
# ---------------------------------------------------------------------------
text = TRANSPORT.read_text(encoding='utf-8')
if 'WFGG_RADAR_MANUAL_SEARCH_STOP_TRANSPORT_V61911' not in text:
    anchor = '  collectorSearchStatus(id) { return this.request(`/v1/collector/search/status?id=${encodeURIComponent(id)}`, { method: \'GET\' }); }'
    if text.count(anchor) != 1:
        raise SystemExit(f'V61911_TRANSPORT_ANCHOR_COUNT={text.count(anchor)}')
    repl = anchor + '''
  // WFGG_RADAR_MANUAL_SEARCH_STOP_TRANSPORT_V61911
  stopCollectorSearch(id) {
    return this.request('/v1/collector/search/stop', { body: { id } });
  }'''
    text = text.replace(anchor, repl, 1)
TRANSPORT.write_text(text, encoding='utf-8')

# ---------------------------------------------------------------------------
# Cloudflare Worker API. No Last War token is read or persisted to stop a job.
# ---------------------------------------------------------------------------
text = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_MANUAL_SEARCH_STOP_WORKER_V61911' not in text:
    anchor = "      if (url.pathname === '/api/radar/search' && request.method === 'GET') {"
    if text.count(anchor) != 1:
        raise SystemExit(f'V61911_WORKER_ROUTE_ANCHOR_COUNT={text.count(anchor)}')
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
    text = text.replace(anchor, block + anchor, 1)
WORKER.write_text(text, encoding='utf-8')

# ---------------------------------------------------------------------------
# UI: RECHERCHER <-> STOP on the same button.
# ---------------------------------------------------------------------------
text = UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_MANUAL_SEARCH_STOP_UI_V61911' not in text:
    css_anchor = '.go:disabled{filter:grayscale(.8);opacity:.55}'
    if text.count(css_anchor) != 1:
        raise SystemExit(f'V61911_UI_CSS_ANCHOR_COUNT={text.count(css_anchor)}')
    text = text.replace(
        css_anchor,
        css_anchor + '.go.stop{background:linear-gradient(#e58671,#983d32);border-color:#d88b78;color:#fff3ee;box-shadow:inset 0 1px #fff5,0 5px 0 #52251f,0 8px 16px #0008}',
        1,
    )

    state_anchor = "const $=id=>document.getElementById(id);const screen=$('screen'),go=$('go'),result=$('result'),login=$('login'),target=$('target');let phaseTimer=null,audioCtx=null;"
    if text.count(state_anchor) != 1:
        raise SystemExit(f'V61911_UI_STATE_ANCHOR_COUNT={text.count(state_anchor)}')
    state_repl = state_anchor + """
/* WFGG_RADAR_MANUAL_SEARCH_STOP_UI_V61911 */
let manualSearchRunning=false,manualSearchStopping=false,manualSearchStopPending=false,manualSearchJobId='';
function setManualSearchButton(running=false,stopping=false){manualSearchRunning=Boolean(running);manualSearchStopping=Boolean(stopping);go.classList.toggle('stop',manualSearchRunning);go.disabled=manualSearchStopping;go.textContent=manualSearchRunning?(manualSearchStopping?'ARRÊT…':'STOP'):'RECHERCHER'}
async function requestManualSearchStop(){if(!manualSearchRunning||manualSearchStopping)return true;manualSearchStopPending=true;if(!manualSearchJobId){setStatus('ARRÊT DEMANDÉ','Initialisation du cycle en cours…');return true}manualSearchStopping=true;setManualSearchButton(true,true);setStatus('ARRÊT DU RADAR','Interruption de la recherche manuelle…');try{await api('/api/radar/search/stop',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id:manualSearchJobId})});return true}catch(err){manualSearchStopping=false;manualSearchStopPending=false;setManualSearchButton(true,false);setStatus('ARRÊT IMPOSSIBLE',String(err.message||err),'error');return false}}
"""
    text = text.replace(state_anchor, state_repl, 1)

    start_anchor = "function startScan(q){screen.classList.remove('found');screen.classList.add('scanning');target.classList.remove('hit');result.classList.remove('show');go.disabled=true;steps(1);setStatus('DÉMARRAGE DU CYCLE',q);tone(420,.04,.018);clearInterval(phaseTimer)}"
    if text.count(start_anchor) != 1:
        raise SystemExit(f'V61911_UI_START_SCAN_ANCHOR_COUNT={text.count(start_anchor)}')
    text = text.replace(
        start_anchor,
        "function startScan(q){screen.classList.remove('found');screen.classList.add('scanning');target.classList.remove('hit');result.classList.remove('show');manualSearchJobId='';manualSearchStopPending=false;setManualSearchButton(true,false);steps(1);setStatus('DÉMARRAGE DU CYCLE',q);tone(420,.04,.018);clearInterval(phaseTimer)}",
        1,
    )

    stop_anchor = "function stopScan(){clearInterval(phaseTimer);screen.classList.remove('scanning');go.disabled=false}"
    if text.count(stop_anchor) != 1:
        raise SystemExit(f'V61911_UI_STOP_SCAN_ANCHOR_COUNT={text.count(stop_anchor)}')
    text = text.replace(
        stop_anchor,
        "function stopScan(){clearInterval(phaseTimer);screen.classList.remove('scanning');manualSearchJobId='';manualSearchStopPending=false;setManualSearchButton(false,false)}",
        1,
    )

    run_anchor = "async function runCollectorSearch(q){let job=await loadOrStartCollectorJob(q);rememberCollectorJob(job,q);for(;;){renderJob(job);if(job.status==='SUCCESS'){forgetCollectorJob();return {job,player:job.player||null}}if(job.status==='FAILED'){forgetCollectorJob();throw new Error(job.error||'COLLECTOR_SEARCH_FAILED')}await sleep(2000);job=await fetchCollectorJobResilient(job.id,job);rememberCollectorJob(job,q)}}"
    if text.count(run_anchor) != 1:
        raise SystemExit(f'V61911_UI_RUN_ANCHOR_COUNT={text.count(run_anchor)}')
    run_repl = """async function runCollectorSearch(q){let job=await loadOrStartCollectorJob(q);manualSearchJobId=String(job.id||'');rememberCollectorJob(job,q);if(manualSearchStopPending)await requestManualSearchStop();for(;;){renderJob(job);if(job.status==='SUCCESS'){forgetCollectorJob();return {job,player:job.player||null}}if(job.status==='FAILED'){forgetCollectorJob();const e=new Error(job.error||'COLLECTOR_SEARCH_FAILED');e.code=String(job.error||'COLLECTOR_SEARCH_FAILED');throw e}await sleep(2000);job=await fetchCollectorJobResilient(job.id,job);manualSearchJobId=String(job.id||manualSearchJobId);rememberCollectorJob(job,q)}}"""
    text = text.replace(run_anchor, run_repl, 1)

    submit_anchor = "$('searchForm').onsubmit=async e=>{e.preventDefault();const q=$('q').value.trim();if(!q)return;startScan(q);try{"
    if text.count(submit_anchor) != 1:
        raise SystemExit(f'V61911_UI_SUBMIT_ANCHOR_COUNT={text.count(submit_anchor)}')
    submit_repl = "$('searchForm').onsubmit=async e=>{e.preventDefault();if(manualSearchRunning){await requestManualSearchStop();return}const q=$('q').value.trim();if(!q)return;startScan(q);try{"
    text = text.replace(submit_anchor, submit_repl, 1)

    catch_anchor = "}catch(err){stopScan();screen.classList.remove('found');if(err.status===401){"
    if text.count(catch_anchor) != 1:
        raise SystemExit(f'V61911_UI_CATCH_ANCHOR_COUNT={text.count(catch_anchor)}')
    catch_repl = "}catch(err){stopScan();screen.classList.remove('found');if(String(err?.code||err?.message||'')==='MANUAL_SEARCH_STOPPED'){steps(0);setStatus('RADAR ARRÊTÉ','Recherche manuelle interrompue','ok');$('federatedTitle').textContent='COLLECTOR FÉDÉRÉ · ARRÊTÉ';$('federatedMeta').textContent='Recherche manuelle interrompue par l’utilisateur.';tone(300,.06,.018)}else if(err.status===401){"
    text = text.replace(catch_anchor, catch_repl, 1)

UI.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# Connector unit tests for the one-job manual stop contract.
# ---------------------------------------------------------------------------
if not TEST.exists():
    TEST.write_text(r'''package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func withIsolatedManualStopStoresV61911(t *testing.T) {
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
	withIsolatedManualStopStoresV61911(t)
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
	body := []byte(`{"id":"` + j.ID + `"}`)
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
	withIsolatedManualStopStoresV61911(t)
	j := radarCollectorJobs.add("Player")
	radarCollectorJobs.update(j.ID, func(x *collectorJob) {
		x.Status = "SUCCESS"
		x.Phase = "DONE"
		x.FinishedAt = utcNow()
	})

	rr := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/collector/search/stop", nil)
	body := []byte(`{"id":"` + j.ID + `"}`)
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
