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

    start_fn = "function startScan(q){"
    stop_fn = "function stopScan(){"
    start_pos = text.find(start_fn)
    stop_pos = text.find(stop_fn, start_pos + len(start_fn))
    if start_pos < 0 or stop_pos < 0:
        raise SystemExit('V61911_UI_STARTSCAN_FUNCTION_MISSING')
    start_segment = text[start_pos:stop_pos]
    disabled_anchor = 'go.disabled=true;'
    if start_segment.count(disabled_anchor) != 1:
        raise SystemExit(f'V61911_UI_STARTSCAN_DISABLE_COUNT={start_segment.count(disabled_anchor)}')
    start_segment = start_segment.replace(
        disabled_anchor,
        "manualSearchJobId='';manualSearchStopPending=false;setManualSearchButton(true,false);",
        1,
    )
    text = text[:start_pos] + start_segment + text[stop_pos:]

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

    submit_anchor = "$('searchForm').onsubmit=async e=>{e.preventDefault();"
    if text.count(submit_anchor) != 1:
        raise SystemExit(f'V61911_UI_SUBMIT_ANCHOR_COUNT={text.count(submit_anchor)}')
    submit_repl = submit_anchor + "if(manualSearchRunning){await requestManualSearchStop();return}"
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
