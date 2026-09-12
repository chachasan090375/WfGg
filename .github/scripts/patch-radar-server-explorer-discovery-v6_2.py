#!/usr/bin/env python3
from pathlib import Path

JOBS = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
s = JOBS.read_text(encoding='utf-8')

route_marker = '// SERVER_EXPLORER_DISCOVERY_V61\n'
if 'SERVER_EXPLORER_DISCOVERY_V62_ROUTE' not in s:
    route = r'''// SERVER_EXPLORER_DISCOVERY_V62_ROUTE
	if strings.HasPrefix(strings.ToLower(strings.TrimSpace(query)), "@discover:auto") {
		s.handleServerDiscoveryV62(ctx, token, query, jobID)
		return
	}
	'''
    if s.count(route_marker) != 1:
        raise SystemExit(f'V62_ROUTE_ANCHOR expected 1 match, got {s.count(route_marker)}')
    s = s.replace(route_marker, route + route_marker, 1)

helper_anchor = 'var errPlayerNotFound = errors.New("COLLECTOR_PLAYER_NOT_FOUND")\n'
if 'SERVER_EXPLORER_DISCOVERY_V62_STATE' not in s:
    helper = r'''// SERVER_EXPLORER_DISCOVERY_V62_STATE
const serverDiscoveryV62Path = "/opt/wfgg-radar/state/server-discovery-v62.json"
const serverDiscoveryV62Window = 11
const serverDiscoveryV62MaxWindowsPerRun = 5

type serverDiscoveryV62State struct {
	Version      int               `json:"version"`
	Anchor       int               `json:"anchor"`
	NextLow      int               `json:"nextLow"`
	NextHigh     int               `json:"nextHigh"`
	LowStopped   bool              `json:"lowStopped"`
	HighStopped  bool              `json:"highStopped"`
	Results      map[string]string `json:"results"`
	Runs         int               `json:"runs"`
	UpdatedAt    string            `json:"updatedAt"`
}

var serverDiscoveryV62Mu sync.Mutex

func newServerDiscoveryV62State(anchor int) serverDiscoveryV62State {
	return serverDiscoveryV62State{
		Version: 2,
		Anchor: anchor,
		NextLow: anchor - 6,
		NextHigh: anchor + 6,
		Results: map[string]string{},
		UpdatedAt: utcNow(),
	}
}

func loadServerDiscoveryV62() (serverDiscoveryV62State, error) {
	raw, err := os.ReadFile(serverDiscoveryV62Path)
	if err != nil { return serverDiscoveryV62State{}, err }
	var st serverDiscoveryV62State
	if err := json.Unmarshal(raw, &st); err != nil { return serverDiscoveryV62State{}, err }
	if st.Version != 2 || st.Anchor <= 0 { return serverDiscoveryV62State{}, errors.New("SERVER_DISCOVERY_STATE_INVALID") }
	if st.Results == nil { st.Results = map[string]string{} }
	return st, nil
}

func saveServerDiscoveryV62(st serverDiscoveryV62State) error {
	st.UpdatedAt = utcNow()
	if err := os.MkdirAll("/opt/wfgg-radar/state", 0750); err != nil { return err }
	raw, err := json.MarshalIndent(st, "", "  ")
	if err != nil { return err }
	tmp := serverDiscoveryV62Path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0600); err != nil { return err }
	return os.Rename(tmp, serverDiscoveryV62Path)
}

func parseServerDiscoveryV62Query(query string) (anchor int, reset bool, err error) {
	raw := strings.TrimSpace(query)
	low := strings.ToLower(raw)
	if low == "@discover:auto" { return 0, false, nil }
	if !strings.HasPrefix(low, "@discover:auto:") { return 0, false, errors.New("SERVER_DISCOVERY_AUTO_QUERY_INVALID") }
	part := strings.TrimSpace(raw[len("@discover:auto:"):])
	if strings.HasSuffix(strings.ToLower(part), ":reset") {
		reset = true
		part = strings.TrimSpace(part[:len(part)-len(":reset")])
	}
	n, e := strconv.Atoi(part)
	if e != nil || n <= 5 || n > 999994 { return 0, false, errors.New("SERVER_DISCOVERY_AUTO_CENTER_INVALID") }
	return n, reset, nil
}

func discoveryRangeV62(lo, hi int) []string {
	if lo < 1 { lo = 1 }
	if hi > 999999 { hi = 999999 }
	out := make([]string, 0, hi-lo+1)
	for n := lo; n <= hi; n++ { out = append(out, strconv.Itoa(n)) }
	return out
}

func (s *server) probeDiscoveryWindowV62(ctx context.Context, scanner protocol.ServerBatchScanner, token, jobID, direction string, ids []string, st *serverDiscoveryV62State) (int, error) {
	started := time.Now()
	rows, err := scanner.ProbeServerRegions(ctx, token, ids)
	if err != nil { return 0, err }
	accessible := 0
	for _, row := range rows {
		status := "FAILED"
		if row.Accessible { status = "ACCESSIBLE"; accessible++ }
		st.Results[row.ServerID] = status
	}
	if err := saveServerDiscoveryV62(*st); err != nil { return accessible, err }
	slog.Info("SERVER_DISCOVERY_V62_SENTINEL", "jobId", jobID, "stage", "WINDOW_DONE", "direction", direction, "low", ids[0], "high", ids[len(ids)-1], "tested", len(rows), "accessible", accessible, "durationMs", time.Since(started).Milliseconds())
	return accessible, nil
}

func (s *server) handleServerDiscoveryV62(ctx context.Context, token, query, jobID string) {
	anchor, reset, err := parseServerDiscoveryV62Query(query)
	if err != nil {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status="FAILED"; j.Phase="SERVER_DISCOVERY_V62_FAILED"; j.Error=err.Error(); j.FinishedAt=utcNow() })
		return
	}
	batchScanner, ok := s.game.(protocol.ServerBatchScanner)
	if !ok {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status="FAILED"; j.Phase="SERVER_DISCOVERY_V62_FAILED"; j.Error="SERVER_BATCH_SCANNER_UNAVAILABLE"; j.FinishedAt=utcNow() })
		return
	}

	serverDiscoveryV62Mu.Lock()
	defer serverDiscoveryV62Mu.Unlock()

	st, loadErr := loadServerDiscoveryV62()
	if anchor > 0 && (reset || loadErr != nil || st.Anchor != anchor) {
		st = newServerDiscoveryV62State(anchor)
		loadErr = nil
	}
	if loadErr != nil {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status="FAILED"; j.Phase="SERVER_DISCOVERY_V62_FAILED"; j.Error="SERVER_DISCOVERY_STATE_MISSING_USE_EXPLICIT_CENTER"; j.FinishedAt=utcNow() })
		return
	}
	if st.Results == nil { st.Results = map[string]string{} }

	radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Strategy="SERVER_EXPLORER_V62_RESUMABLE"; j.Phase="SERVER_DISCOVERY_V62"; j.Region=0; j.Regions=serverDiscoveryV62MaxWindowsPerRun })
	slog.Info("SERVER_DISCOVERY_V62_SENTINEL", "jobId", jobID, "stage", "START", "anchor", st.Anchor, "nextLow", st.NextLow, "nextHigh", st.NextHigh, "lowStopped", st.LowStopped, "highStopped", st.HighStopped, "known", len(st.Results))

	windows := 0
	if len(st.Results) == 0 {
		ids := discoveryRangeV62(st.Anchor-5, st.Anchor+5)
		probeCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
		_, err = s.probeDiscoveryWindowV62(probeCtx, batchScanner, token, jobID, "CENTER", ids, &st)
		cancel()
		if err != nil {
			radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status="FAILED"; j.Phase="SERVER_DISCOVERY_V62_FAILED"; j.Error="SERVER_DISCOVERY_CENTER_PROBE_FAILED"; j.FinishedAt=utcNow() })
			return
		}
		windows++
	}

	for windows < serverDiscoveryV62MaxWindowsPerRun && (!st.LowStopped || !st.HighStopped) {
		if !st.LowStopped && windows < serverDiscoveryV62MaxWindowsPerRun {
			hi := st.NextLow
			lo := hi - (serverDiscoveryV62Window - 1)
			if hi < 1 { st.LowStopped = true } else {
				ids := discoveryRangeV62(lo, hi)
				probeCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
				count, e := s.probeDiscoveryWindowV62(probeCtx, batchScanner, token, jobID, "LOW", ids, &st)
				cancel()
				if e != nil { err = e; break }
				st.NextLow = lo - 1
				if count == 0 { st.LowStopped = true }
				windows++
				_ = saveServerDiscoveryV62(st)
			}
		}
		if !st.HighStopped && windows < serverDiscoveryV62MaxWindowsPerRun {
			lo := st.NextHigh
			hi := lo + (serverDiscoveryV62Window - 1)
			if lo > 999999 { st.HighStopped = true } else {
				ids := discoveryRangeV62(lo, hi)
				probeCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
				count, e := s.probeDiscoveryWindowV62(probeCtx, batchScanner, token, jobID, "HIGH", ids, &st)
				cancel()
				if e != nil { err = e; break }
				st.NextHigh = hi + 1
				if count == 0 { st.HighStopped = true }
				windows++
				_ = saveServerDiscoveryV62(st)
			}
		}
	}

	st.Runs++
	if saveErr := saveServerDiscoveryV62(st); err == nil { err = saveErr }
	if err != nil {
		radarCollectorJobs.update(jobID, func(j *collectorJob) { j.Status="FAILED"; j.Phase="SERVER_DISCOVERY_V62_FAILED"; j.Error="SERVER_DISCOVERY_WINDOW_FAILED"; j.FinishedAt=utcNow() })
		return
	}

	accessible := 0
	failed := 0
	for _, status := range st.Results { if status == "ACCESSIBLE" { accessible++ } else { failed++ } }
	player := map[string]any{
		"pseudo":"SERVER DISCOVERY V6.2",
		"game_uid":"server-discovery-v62",
		"server_id":strconv.Itoa(st.Anchor),
		"discoveryKnown":len(st.Results),
		"discoveryAccessible":accessible,
		"discoveryFailed":failed,
		"discoveryNextLow":st.NextLow,
		"discoveryNextHigh":st.NextHigh,
		"discoveryLowStopped":st.LowStopped,
		"discoveryHighStopped":st.HighStopped,
		"observed_at":utcNow(),
	}
	completeCollectorJob(jobID, player)
	slog.Info("SERVER_DISCOVERY_V62_SENTINEL", "jobId", jobID, "stage", "DONE", "anchor", st.Anchor, "windowsThisRun", windows, "known", len(st.Results), "accessible", accessible, "failed", failed, "nextLow", st.NextLow, "nextHigh", st.NextHigh, "lowStopped", st.LowStopped, "highStopped", st.HighStopped, "runs", st.Runs)
}

'''
    if s.count(helper_anchor) != 1:
        raise SystemExit(f'V62_HELPER_ANCHOR expected 1 match, got {s.count(helper_anchor)}')
    s = s.replace(helper_anchor, helper + helper_anchor, 1)

JOBS.write_text(s, encoding='utf-8')
print('SERVER_EXPLORER_DISCOVERY_V62=PATCHED')
print('SERVER_EXPLORER_DISCOVERY_V62_RESUMABLE=YES')
print('SERVER_EXPLORER_DISCOVERY_V62_WINDOW=11')
print('SERVER_EXPLORER_DISCOVERY_V62_MAX_WINDOWS_PER_RUN=5')
print('SERVER_EXPLORER_DISCOVERY_V62_STATE=/opt/wfgg-radar/state/server-discovery-v62.json')
