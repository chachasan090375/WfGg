#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
MAIN = ROOT / 'cmd/radar-connector/main.go'
JOBS = ROOT / 'cmd/radar-connector/collector_jobs.go'
PASSIVE = ROOT / 'cmd/radar-connector/autocartographer_v634_passive.go'


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# V6.3.4 safety contract:
# - no scheduled/background Last War call
# - no retained gameplay token
# - no /v1/cartographer/tick active probe route
# - passive observations are produced only from an already-running Collector map
# ---------------------------------------------------------------------------
s = MAIN.read_text(encoding='utf-8')

arm_block = '''\t\t// AUTO_CARTOGRAPHER_V633_ARM: any already-verified request carrying a\n\t\t// normal game token refreshes the in-memory watcher token. The token is\n\t\t// never written to disk or logs.\n\t\tmaybeArmAutoCartographerV633FromBody(s, body)\n'''
if arm_block in s:
    s = s.replace(arm_block, '', 1)
elif 'maybeArmAutoCartographerV633FromBody(s, body)' in s:
    s = s.replace('\t\tmaybeArmAutoCartographerV633FromBody(s, body)\n', '', 1)

v633_route = '''\t// AUTO_CARTOGRAPHER_V633_ROUTE\n\tmux.HandleFunc("POST /v1/cartographer/tick", s.signed(s.autoCartographerV633TickHTTP))\n'''
if v633_route in s:
    s = s.replace(v633_route, '', 1)

status_anchor = '''\tmux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))\n'''
status_route = status_anchor + '''\t// AUTO_CARTOGRAPHER_V634_PASSIVE_ROUTE\n\tmux.HandleFunc("GET /v1/cartographer/status", s.signed(s.autoCartographerV634StatusHTTP))\n'''
if 'AUTO_CARTOGRAPHER_V634_PASSIVE_ROUTE' not in s:
    s = once(s, status_anchor, status_route, 'v634 status route')

MAIN.write_text(s, encoding='utf-8')

# Hook passive observation into work Collector is ALREADY doing. These calls do
# not initiate any game request: they only inspect the []protocol.Player that the
# normal search loop has already received.
s = JOBS.read_text(encoding='utf-8')

start_anchor = '''func (s *server) runCollectorSearch(jobID, token, query string) {\n\tctx, cancel := context.WithTimeout(context.Background(), 12*time.Minute)\n\tdefer cancel()\n'''
start_new = start_anchor + '''\tpassiveV634Start(jobID)\n\tdefer passiveV634Abort(jobID)\n'''
if 'passiveV634Start(jobID)' not in s:
    s = once(s, start_anchor, start_new, 'v634 collector start hook')

observe_anchor = '''\t\tplayers, err := regionScanner.ScanPlayerRegion(ctx, token, "*", region)\n\t\tif err != nil {\n\t\t\t_ = collectorFinishCycle(context.Background(), cycle.ID, "FAILED", "MAP_REGION_FAILED")\n\t\t\tfail("MAP_REGION_FAILED")\n\t\t\treturn\n\t\t}\n'''
observe_new = observe_anchor + '''\t\tpassiveV634Observe(jobID, region, players)\n'''
if 'passiveV634Observe(jobID, region, players)' not in s:
    s = once(s, observe_anchor, observe_new, 'v634 collector observation hook')

commit_anchor = '''\t}\n\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "ENRICHING"; j.Region = 9 })\n'''
commit_new = '''\t}\n\n\tpassiveV634Commit(jobID)\n\tradarCollectorJobs.update(jobID, func(j *collectorJob) { j.Phase = "ENRICHING"; j.Region = 9 })\n'''
if 'passiveV634Commit(jobID)' not in s:
    s = once(s, commit_anchor, commit_new, 'v634 collector commit hook')

JOBS.write_text(s, encoding='utf-8')

PASSIVE.write_text(r'''package main

import (
    "encoding/json"
    "fmt"
    "net/http"
    "os"
    "sort"
    "strings"
    "sync"
    "time"

    "wfgg-radar-connector/internal/protocol"
)

// AUTO_CARTOGRAPHER_V634_PASSIVE
//
// Safety invariant: this component NEVER opens a Last War connection, NEVER
// stores a gameplay credential and NEVER starts a goroutine/ticker. It only
// consumes player rows already returned by a user-initiated Collector scan.

const passiveV634StatePath = "/opt/wfgg-radar/state/auto-cartographer-v634-passive.json"

type passiveV634Region struct {
    Region            int    `json:"region"`
    Decoded           int    `json:"decoded"`
    DominantServerID  string `json:"dominantServerId"`
    DominantCount     int    `json:"dominantCount"`
    DistinctServerIDs int    `json:"distinctServerIds"`
}

type passiveV634Context struct {
    Fingerprint     string              `json:"fingerprint"`
    FirstSeen       string              `json:"firstSeen"`
    LastSeen        string              `json:"lastSeen"`
    Visits          int                 `json:"visits"`
    UniqueUIDs      int                 `json:"uniqueUIDs"`
    DistinctServers int                 `json:"distinctServers"`
    Regions         []passiveV634Region `json:"regions"`
}

type passiveV634State struct {
    Version         int                           `json:"version"`
    Mode            string                        `json:"mode"`
    ActiveProbes    bool                          `json:"activeProbes"`
    HoldsGameToken  bool                          `json:"holdsGameToken"`
    BackgroundCalls bool                          `json:"backgroundGameCalls"`
    LastObservedAt  string                        `json:"lastObservedAt"`
    LastFingerprint string                        `json:"lastFingerprint"`
    Contexts        map[string]passiveV634Context `json:"contexts"`
}

type passiveV634Scan struct {
    regions map[int]passiveV634Region
    uids    map[string]struct{}
    servers map[string]struct{}
}

var passiveV634Runtime = struct {
    sync.Mutex
    scans map[string]*passiveV634Scan
}{scans: map[string]*passiveV634Scan{}}

func passiveV634Now() string { return time.Now().UTC().Format(time.RFC3339Nano) }

func passiveV634Dominant(players []protocol.Player) (string, int, int, map[string]struct{}, map[string]struct{}) {
    counts := map[string]int{}
    uids := map[string]struct{}{}
    servers := map[string]struct{}{}
    for _, p := range players {
        uid := strings.TrimSpace(p.GameUID)
        if uid != "" { uids[uid] = struct{}{} }
        sid := strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS")
        if sid == "" { continue }
        counts[sid]++
        servers[sid] = struct{}{}
    }
    best, bestN := "", 0
    for sid, n := range counts {
        if n > bestN || (n == bestN && (best == "" || sid < best)) {
            best, bestN = sid, n
        }
    }
    return best, bestN, len(counts), uids, servers
}

func passiveV634Start(jobID string) {
    passiveV634Runtime.Lock()
    defer passiveV634Runtime.Unlock()
    passiveV634Runtime.scans[jobID] = &passiveV634Scan{
        regions: map[int]passiveV634Region{},
        uids: map[string]struct{}{},
        servers: map[string]struct{}{},
    }
}

func passiveV634Abort(jobID string) {
    passiveV634Runtime.Lock()
    defer passiveV634Runtime.Unlock()
    delete(passiveV634Runtime.scans, jobID)
}

func passiveV634Observe(jobID string, region int, players []protocol.Player) {
    dom, domN, distinct, uids, servers := passiveV634Dominant(players)
    passiveV634Runtime.Lock()
    defer passiveV634Runtime.Unlock()
    scan := passiveV634Runtime.scans[jobID]
    if scan == nil { return }
    scan.regions[region] = passiveV634Region{
        Region: region, Decoded: len(players), DominantServerID: dom,
        DominantCount: domN, DistinctServerIDs: distinct,
    }
    for uid := range uids { scan.uids[uid] = struct{}{} }
    for sid := range servers { scan.servers[sid] = struct{}{} }
}

func passiveV634Load() passiveV634State {
    st := passiveV634State{
        Version: 1, Mode: "PASSIVE_ONLY", ActiveProbes: false,
        HoldsGameToken: false, BackgroundCalls: false,
        Contexts: map[string]passiveV634Context{},
    }
    b, err := os.ReadFile(passiveV634StatePath)
    if err != nil { return st }
    var disk passiveV634State
    if json.Unmarshal(b, &disk) != nil || disk.Version != 1 { return st }
    if disk.Contexts == nil { disk.Contexts = map[string]passiveV634Context{} }
    disk.Mode = "PASSIVE_ONLY"
    disk.ActiveProbes = false
    disk.HoldsGameToken = false
    disk.BackgroundCalls = false
    return disk
}

func passiveV634Save(st passiveV634State) error {
    if err := os.MkdirAll("/opt/wfgg-radar/state", 0750); err != nil { return err }
    b, err := json.MarshalIndent(st, "", "  ")
    if err != nil { return err }
    tmp := passiveV634StatePath + ".tmp"
    if err := os.WriteFile(tmp, append(b, '\n'), 0640); err != nil { return err }
    return os.Rename(tmp, passiveV634StatePath)
}

func passiveV634Commit(jobID string) {
    passiveV634Runtime.Lock()
    scan := passiveV634Runtime.scans[jobID]
    if scan == nil || len(scan.regions) != 9 {
        passiveV634Runtime.Unlock()
        return
    }
    regions := make([]passiveV634Region, 0, 9)
    parts := make([]string, 0, 9)
    for i := 0; i < 9; i++ {
        r, ok := scan.regions[i]
        if !ok { passiveV634Runtime.Unlock(); return }
        regions = append(regions, r)
        parts = append(parts, fmt.Sprintf("r%d:%s", i, r.DominantServerID))
    }
    uidCount, serverCount := len(scan.uids), len(scan.servers)
    delete(passiveV634Runtime.scans, jobID)
    passiveV634Runtime.Unlock()

    fp := strings.Join(parts, "|")
    now := passiveV634Now()
    st := passiveV634Load()
    ctx := st.Contexts[fp]
    if ctx.FirstSeen == "" { ctx.FirstSeen = now }
    ctx.Fingerprint = fp
    ctx.LastSeen = now
    ctx.Visits++
    ctx.UniqueUIDs = uidCount
    ctx.DistinctServers = serverCount
    ctx.Regions = regions
    st.Contexts[fp] = ctx
    st.LastObservedAt = now
    st.LastFingerprint = fp
    _ = passiveV634Save(st)
    fmt.Printf("%s INFO AUTO_CARTOGRAPHER_V634_PASSIVE stage=OBSERVED fingerprint=%s uniqueUIDs=%d distinctServers=%d source=EXISTING_COLLECTOR_SCAN\n", now, fp, uidCount, serverCount)
}

func (s *server) autoCartographerV634StatusHTTP(w http.ResponseWriter, _ *http.Request, _ []byte) {
    st := passiveV634Load()
    keys := make([]string, 0, len(st.Contexts))
    for k := range st.Contexts { keys = append(keys, k) }
    sort.Strings(keys)
    writeJSON(w, http.StatusOK, map[string]any{
        "ok": true,
        "version": "6.3.4",
        "mode": "PASSIVE_ONLY",
        "activeProbes": false,
        "holdsGameToken": false,
        "backgroundGameCalls": false,
        "lastObservedAt": st.LastObservedAt,
        "lastFingerprint": st.LastFingerprint,
        "contextCount": len(st.Contexts),
        "fingerprints": keys,
        "state": st,
    })
}
''', encoding='utf-8')

print('AUTO_CARTOGRAPHER_V634_PASSIVE=PATCHED')
print('AUTO_CARTOGRAPHER_V634_ACTIVE_PROBES=NO')
print('AUTO_CARTOGRAPHER_V634_GAME_TOKEN_RETENTION=NO')
print('AUTO_CARTOGRAPHER_V634_BACKGROUND_GAME_CALLS=NO')
print('AUTO_CARTOGRAPHER_V634_STATUS=/v1/cartographer/status')
