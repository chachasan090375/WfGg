#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
PASSIVE = ROOT / 'cmd/radar-connector/autocartographer_v634_passive.go'

if not PASSIVE.exists():
    raise SystemExit('V635 requires V634 passive patch first')

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

// AUTO_CARTOGRAPHER_V635_PASSIVE_CHANGE
//
// Safety invariant inherited from V6.3.4:
//   - no Last War connection is opened by this component
//   - no gameplay token is retained
//   - no ticker/goroutine/background probe exists
//   - observations come only from player rows already returned by an existing
//     user-initiated Collector scan
//
// V6.3.5 adds passive context-change detection. A new topology fingerprint must
// be observed by two complete Collector maps before it becomes the current
// context. This is intentionally called a context change, not a teleport, since
// the VPS cannot prove the user's in-game action without a phone-side signal.

const (
    passiveV635StatePath  = "/opt/wfgg-radar/state/auto-cartographer-v635-passive-change.json"
    passiveV634LegacyPath = "/opt/wfgg-radar/state/auto-cartographer-v634-passive.json"
)

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

type passiveV635Change struct {
    FromFingerprint string `json:"fromFingerprint"`
    ToFingerprint   string `json:"toFingerprint"`
    ConfirmedAt     string `json:"confirmedAt"`
    Confirmations   int    `json:"confirmations"`
    Source          string `json:"source"`
}

type passiveV634State struct {
    Version              int                           `json:"version"`
    Mode                 string                        `json:"mode"`
    ActiveProbes         bool                          `json:"activeProbes"`
    HoldsGameToken       bool                          `json:"holdsGameToken"`
    BackgroundCalls      bool                          `json:"backgroundGameCalls"`
    LastObservedAt       string                        `json:"lastObservedAt"`
    LastFingerprint      string                        `json:"lastFingerprint,omitempty"`
    CurrentFingerprint   string                        `json:"currentFingerprint,omitempty"`
    CandidateFingerprint string                        `json:"candidateFingerprint,omitempty"`
    CandidateCount       int                           `json:"candidateCount"`
    LastChangeAt         string                        `json:"lastChangeAt,omitempty"`
    Contexts             map[string]passiveV634Context `json:"contexts"`
    Changes              []passiveV635Change           `json:"changes,omitempty"`
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

func passiveV635DefaultState() passiveV634State {
    return passiveV634State{
        Version: 2,
        Mode: "PASSIVE_CHANGE_DETECTOR",
        ActiveProbes: false,
        HoldsGameToken: false,
        BackgroundCalls: false,
        Contexts: map[string]passiveV634Context{},
        Changes: []passiveV635Change{},
    }
}

func passiveV634Load() passiveV634State {
    st := passiveV635DefaultState()
    if b, err := os.ReadFile(passiveV635StatePath); err == nil {
        var disk passiveV634State
        if json.Unmarshal(b, &disk) == nil && disk.Version == 2 {
            if disk.Contexts == nil { disk.Contexts = map[string]passiveV634Context{} }
            if disk.Changes == nil { disk.Changes = []passiveV635Change{} }
            disk.Mode = "PASSIVE_CHANGE_DETECTOR"
            disk.ActiveProbes = false
            disk.HoldsGameToken = false
            disk.BackgroundCalls = false
            return disk
        }
    }

    // One-time non-secret migration of the V6.3.4 passive baseline/context DB.
    if b, err := os.ReadFile(passiveV634LegacyPath); err == nil {
        var old passiveV634State
        if json.Unmarshal(b, &old) == nil {
            if old.Contexts != nil { st.Contexts = old.Contexts }
            st.LastObservedAt = old.LastObservedAt
            if strings.TrimSpace(old.CurrentFingerprint) != "" {
                st.CurrentFingerprint = old.CurrentFingerprint
            } else {
                st.CurrentFingerprint = old.LastFingerprint
            }
            if st.CurrentFingerprint != "" { st.LastChangeAt = old.LastObservedAt }
        }
    }
    return st
}

func passiveV634Save(st passiveV634State) error {
    if err := os.MkdirAll("/opt/wfgg-radar/state", 0750); err != nil { return err }
    st.Version = 2
    st.Mode = "PASSIVE_CHANGE_DETECTOR"
    st.ActiveProbes = false
    st.HoldsGameToken = false
    st.BackgroundCalls = false
    b, err := json.MarshalIndent(st, "", "  ")
    if err != nil { return err }
    tmp := passiveV635StatePath + ".tmp"
    if err := os.WriteFile(tmp, append(b, '\n'), 0640); err != nil { return err }
    return os.Rename(tmp, passiveV635StatePath)
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

    stage := "UNCHANGED"
    confirmations := 0
    from := st.CurrentFingerprint
    if st.CurrentFingerprint == "" {
        st.CurrentFingerprint = fp
        st.CandidateFingerprint = ""
        st.CandidateCount = 0
        st.LastChangeAt = now
        stage = "BASELINE"
    } else if fp == st.CurrentFingerprint {
        st.CandidateFingerprint = ""
        st.CandidateCount = 0
        stage = "UNCHANGED"
    } else {
        if fp == st.CandidateFingerprint {
            st.CandidateCount++
        } else {
            st.CandidateFingerprint = fp
            st.CandidateCount = 1
        }
        confirmations = st.CandidateCount
        stage = "CHANGE_CANDIDATE"
        if st.CandidateCount >= 2 {
            change := passiveV635Change{
                FromFingerprint: st.CurrentFingerprint,
                ToFingerprint: fp,
                ConfirmedAt: now,
                Confirmations: st.CandidateCount,
                Source: "EXISTING_COLLECTOR_SCAN",
            }
            st.Changes = append(st.Changes, change)
            if len(st.Changes) > 32 { st.Changes = st.Changes[len(st.Changes)-32:] }
            st.CurrentFingerprint = fp
            st.CandidateFingerprint = ""
            st.CandidateCount = 0
            st.LastChangeAt = now
            stage = "CHANGE_CONFIRMED"
        }
    }

    _ = passiveV634Save(st)
    fmt.Printf("%s INFO AUTO_CARTOGRAPHER_V635_PASSIVE_CHANGE stage=%s fingerprint=%s from=%s confirmations=%d uniqueUIDs=%d distinctServers=%d source=EXISTING_COLLECTOR_SCAN\n", now, stage, fp, from, confirmations, uidCount, serverCount)
}

func (s *server) autoCartographerV634StatusHTTP(w http.ResponseWriter, _ *http.Request, _ []byte) {
    st := passiveV634Load()
    keys := make([]string, 0, len(st.Contexts))
    for k := range st.Contexts { keys = append(keys, k) }
    sort.Strings(keys)
    var latest any = nil
    if len(st.Changes) > 0 { latest = st.Changes[len(st.Changes)-1] }
    writeJSON(w, http.StatusOK, map[string]any{
        "ok": true,
        "version": "6.3.5",
        "mode": "PASSIVE_CHANGE_DETECTOR",
        "activeProbes": false,
        "holdsGameToken": false,
        "backgroundGameCalls": false,
        "detectionSource": "EXISTING_COLLECTOR_SCAN",
        "lastObservedAt": st.LastObservedAt,
        "currentFingerprint": st.CurrentFingerprint,
        "candidateFingerprint": st.CandidateFingerprint,
        "candidateCount": st.CandidateCount,
        "confirmationsRequired": 2,
        "lastChangeAt": st.LastChangeAt,
        "changeCount": len(st.Changes),
        "latestChange": latest,
        "contextCount": len(st.Contexts),
        "fingerprints": keys,
        "state": st,
    })
}
''', encoding='utf-8')

print('AUTO_CARTOGRAPHER_V635_PASSIVE_CHANGE=PATCHED')
print('AUTO_CARTOGRAPHER_V635_ACTIVE_PROBES=NO')
print('AUTO_CARTOGRAPHER_V635_GAME_TOKEN_RETENTION=NO')
print('AUTO_CARTOGRAPHER_V635_BACKGROUND_GAME_CALLS=NO')
print('AUTO_CARTOGRAPHER_V635_CONFIRMATIONS=2')
