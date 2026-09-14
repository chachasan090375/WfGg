package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"wfgg-radar-connector/internal/protocol"
)

// AUTO_CARTOGRAPHER_V633
//
// The watcher never changes the account server and never brute-forces server IDs.
// It observes only the world exposed by the account's legitimate session. A cheap
// 3-region fingerprint is sampled periodically. A changed fingerprint must be
// observed twice before a full 9-region cartography + Collector ingestion runs.
// The gameplay token stays memory-only and is refreshed by normal Radar requests.

const (
	autoCartographerV633StatePath = "/opt/wfgg-radar/state/auto-cartographer-v633.json"
	autoCartographerV633Interval  = 45 * time.Second
)

var autoCartographerV633ProbeRegions = []int{1, 2, 3}

type autoCartographerV633Region struct {
	Region            int    `json:"region"`
	Decoded           int    `json:"decoded"`
	Accepted          int    `json:"accepted,omitempty"`
	DominantServerID  string `json:"dominantServerId"`
	DominantCount     int    `json:"dominantCount"`
	DistinctServerIDs int    `json:"distinctServerIds"`
}

type autoCartographerV633Context struct {
	Fingerprint     string                         `json:"fingerprint"`
	FirstSeen       string                         `json:"firstSeen"`
	LastSeen        string                         `json:"lastSeen"`
	Visits          int                            `json:"visits"`
	Decoded         int                            `json:"decoded"`
	Accepted        int                            `json:"accepted"`
	UniqueUIDs      int                            `json:"uniqueUIDs"`
	DistinctServers int                            `json:"distinctServers"`
	Regions         []autoCartographerV633Region   `json:"regions"`
}

type autoCartographerV633State struct {
	Version              int                                  `json:"version"`
	Enabled              bool                                 `json:"enabled"`
	IntervalSeconds      int                                  `json:"intervalSeconds"`
	ProbeRegions         []int                                `json:"probeRegions"`
	LastFingerprint      string                               `json:"lastFingerprint"`
	CandidateFingerprint string                               `json:"candidateFingerprint"`
	CandidateCount       int                                  `json:"candidateCount"`
	LastProbeAt          string                               `json:"lastProbeAt"`
	LastChangeAt         string                               `json:"lastChangeAt"`
	Contexts             map[string]autoCartographerV633Context `json:"contexts"`
}

var autoCartographerV633Runtime = struct {
	sync.Mutex
	started bool
	token   string
	state   autoCartographerV633State
}{
	state: autoCartographerV633State{
		Version:         1,
		Enabled:         true,
		IntervalSeconds: 45,
		ProbeRegions:    append([]int(nil), autoCartographerV633ProbeRegions...),
		Contexts:        map[string]autoCartographerV633Context{},
	},
}

func autoCartographerV633Enabled() bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv("WFGG_AUTO_CARTOGRAPHER")))
	return v != "0" && v != "false" && v != "off" && v != "disabled"
}

func autoCartographerV633Log(stage string, fields ...any) {
	fmt.Printf("%s INFO AUTO_CARTOGRAPHER_V633_SENTINEL stage=%s", utcNow(), stage)
	for i := 0; i+1 < len(fields); i += 2 {
		fmt.Printf(" %v=%v", fields[i], fields[i+1])
	}
	fmt.Println()
}

func collectorJobsBusyV633() bool {
	radarCollectorJobs.mu.RLock()
	defer radarCollectorJobs.mu.RUnlock()
	for _, j := range radarCollectorJobs.jobs {
		if j != nil && (j.Status == "RUNNING" || j.Status == "QUEUED") {
			return true
		}
	}
	return false
}

func loadAutoCartographerV633Locked() {
	b, err := os.ReadFile(autoCartographerV633StatePath)
	if err != nil {
		return
	}
	var st autoCartographerV633State
	if json.Unmarshal(b, &st) != nil || st.Version != 1 {
		return
	}
	if st.Contexts == nil {
		st.Contexts = map[string]autoCartographerV633Context{}
	}
	if st.IntervalSeconds <= 0 {
		st.IntervalSeconds = 45
	}
	if len(st.ProbeRegions) == 0 {
		st.ProbeRegions = append([]int(nil), autoCartographerV633ProbeRegions...)
	}
	st.Enabled = true
	autoCartographerV633Runtime.state = st
}

func saveAutoCartographerV633Locked() error {
	if err := os.MkdirAll("/opt/wfgg-radar/state", 0750); err != nil {
		return err
	}
	b, err := json.MarshalIndent(autoCartographerV633Runtime.state, "", "  ")
	if err != nil {
		return err
	}
	tmp := autoCartographerV633StatePath + ".tmp"
	if err := os.WriteFile(tmp, append(b, '\n'), 0640); err != nil {
		return err
	}
	return os.Rename(tmp, autoCartographerV633StatePath)
}

func dominantServerV633(players []protocol.Player) (string, int, int) {
	counts := map[string]int{}
	for _, p := range players {
		sid := strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS")
		if sid != "" {
			counts[sid]++
		}
	}
	best := ""
	bestN := 0
	for sid, n := range counts {
		if n > bestN || (n == bestN && (best == "" || sid < best)) {
			best, bestN = sid, n
		}
	}
	return best, bestN, len(counts)
}

func (s *server) autoCartographerV633Fingerprint(token string) (string, []autoCartographerV633Region, error) {
	scanner, ok := s.game.(protocol.RegionScanner)
	if !ok {
		return "", nil, fmt.Errorf("REGION_SCANNER_UNAVAILABLE")
	}
	parts := make([]string, 0, len(autoCartographerV633ProbeRegions))
	summary := make([]autoCartographerV633Region, 0, len(autoCartographerV633ProbeRegions))
	for _, region := range autoCartographerV633ProbeRegions {
		ctx, cancel := context.WithTimeout(context.Background(), 18*time.Second)
		players, err := scanner.ScanPlayerRegion(ctx, token, "*", region)
		cancel()
		if err != nil {
			return "", nil, err
		}
		dom, domN, distinct := dominantServerV633(players)
		parts = append(parts, fmt.Sprintf("r%d:%s", region, dom))
		summary = append(summary, autoCartographerV633Region{
			Region: region, Decoded: len(players), DominantServerID: dom,
			DominantCount: domN, DistinctServerIDs: distinct,
		})
	}
	return strings.Join(parts, "|"), summary, nil
}

func armAutoCartographerV633(s *server, token string) {
	if !autoCartographerV633Enabled() || len(strings.TrimSpace(token)) < 8 {
		return
	}
	autoCartographerV633Runtime.Lock()
	autoCartographerV633Runtime.token = token
	if autoCartographerV633Runtime.started {
		autoCartographerV633Runtime.Unlock()
		return
	}
	loadAutoCartographerV633Locked()
	autoCartographerV633Runtime.started = true
	autoCartographerV633Runtime.Unlock()

	autoCartographerV633Log("WATCHER_START", "intervalSeconds", 45, "probeRegions", "1,2,3", "tokenPersistence", "MEMORY_ONLY")
	go s.autoCartographerV633Loop()
}

func (s *server) autoCartographerV633Loop() {
	// Give the request that armed us time to finish before the first probe.
	timer := time.NewTimer(20 * time.Second)
	defer timer.Stop()
	<-timer.C
	ticker := time.NewTicker(autoCartographerV633Interval)
	defer ticker.Stop()
	for {
		s.autoCartographerV633ProbeOnce()
		<-ticker.C
	}
}

func (s *server) autoCartographerV633ProbeOnce() {
	if collectorJobsBusyV633() {
		autoCartographerV633Log("PROBE_SKIPPED", "reason", "COLLECTOR_BUSY")
		return
	}
	autoCartographerV633Runtime.Lock()
	token := autoCartographerV633Runtime.token
	autoCartographerV633Runtime.Unlock()
	if len(strings.TrimSpace(token)) < 8 {
		autoCartographerV633Log("PROBE_SKIPPED", "reason", "TOKEN_UNAVAILABLE")
		return
	}

	fp, summary, err := s.autoCartographerV633Fingerprint(token)
	if err != nil {
		autoCartographerV633Log("PROBE_ERROR", "error", err.Error())
		return
	}
	now := utcNow()

	autoCartographerV633Runtime.Lock()
	st := &autoCartographerV633Runtime.state
	st.LastProbeAt = now
	if st.LastFingerprint == "" {
		st.LastFingerprint = fp
		st.LastChangeAt = now
		st.CandidateFingerprint = ""
		st.CandidateCount = 0
		_ = saveAutoCartographerV633Locked()
		autoCartographerV633Runtime.Unlock()
		autoCartographerV633Log("BASELINE", "fingerprint", fp, "regions", fmt.Sprint(summary))
		return
	}
	if fp == st.LastFingerprint {
		st.CandidateFingerprint = ""
		st.CandidateCount = 0
		_ = saveAutoCartographerV633Locked()
		autoCartographerV633Runtime.Unlock()
		autoCartographerV633Log("UNCHANGED", "fingerprint", fp)
		return
	}
	if fp == st.CandidateFingerprint {
		st.CandidateCount++
	} else {
		st.CandidateFingerprint = fp
		st.CandidateCount = 1
	}
	candidateCount := st.CandidateCount
	_ = saveAutoCartographerV633Locked()
	autoCartographerV633Runtime.Unlock()
	autoCartographerV633Log("CHANGE_CANDIDATE", "fingerprint", fp, "confirmations", candidateCount)
	if candidateCount < 2 {
		return
	}

	s.autoCartographerV633FullMap(token, fp)
}

func (s *server) autoCartographerV633FullMap(token, fingerprint string) {
	scanner, ok := s.game.(protocol.RegionScanner)
	if !ok {
		autoCartographerV633Log("MAP_ERROR", "error", "REGION_SCANNER_UNAVAILABLE")
		return
	}
	jobID := fmt.Sprintf("autocart-v633-%d", time.Now().UnixNano())
	autoCartographerV633Log("MAP_START", "jobId", jobID, "fingerprint", fingerprint)

	regions := make([]autoCartographerV633Region, 0, 9)
	seenUID := map[string]struct{}{}
	serverSet := map[string]struct{}{}
	totalDecoded := 0
	totalAccepted := 0

	for region := 0; region < 9; region++ {
		ctx, cancel := context.WithTimeout(context.Background(), 22*time.Second)
		players, err := scanner.ScanPlayerRegion(ctx, token, "*", region)
		cancel()
		if err != nil {
			autoCartographerV633Log("MAP_REGION_ERROR", "jobId", jobID, "region", region, "error", err.Error())
			return
		}
		dom, domN, distinct := dominantServerV633(players)
		for _, p := range players {
			uid := strings.TrimSpace(p.GameUID)
			if uid != "" {
				seenUID[uid] = struct{}{}
			}
			sid := strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS")
			if sid != "" {
				serverSet[sid] = struct{}{}
			}
		}
		accepted, ingestErr := collectorIngest(context.Background(), players, 0)
		if ingestErr != nil {
			autoCartographerV633Log("INGEST_ERROR", "jobId", jobID, "region", region, "error", ingestErr.Error())
			accepted = 0
		}
		totalDecoded += len(players)
		totalAccepted += accepted
		regions = append(regions, autoCartographerV633Region{
			Region: region, Decoded: len(players), Accepted: accepted,
			DominantServerID: dom, DominantCount: domN, DistinctServerIDs: distinct,
		})
		autoCartographerV633Log("MAP_REGION_DONE", "jobId", jobID, "region", region, "dominantServerId", dom, "dominantCount", domN, "distinctServerIds", distinct, "decoded", len(players), "accepted", accepted)
	}

	now := utcNow()
	autoCartographerV633Runtime.Lock()
	st := &autoCartographerV633Runtime.state
	ctxState := st.Contexts[fingerprint]
	if ctxState.FirstSeen == "" {
		ctxState.FirstSeen = now
	}
	ctxState.Fingerprint = fingerprint
	ctxState.LastSeen = now
	ctxState.Visits++
	ctxState.Decoded = totalDecoded
	ctxState.Accepted = totalAccepted
	ctxState.UniqueUIDs = len(seenUID)
	ctxState.DistinctServers = len(serverSet)
	ctxState.Regions = regions
	st.Contexts[fingerprint] = ctxState
	st.LastFingerprint = fingerprint
	st.CandidateFingerprint = ""
	st.CandidateCount = 0
	st.LastChangeAt = now
	_ = saveAutoCartographerV633Locked()
	autoCartographerV633Runtime.Unlock()

	autoCartographerV633Log("MAP_DONE", "jobId", jobID, "fingerprint", fingerprint, "decoded", totalDecoded, "accepted", totalAccepted, "uniqueUIDs", len(seenUID), "distinctServers", len(serverSet))
}
