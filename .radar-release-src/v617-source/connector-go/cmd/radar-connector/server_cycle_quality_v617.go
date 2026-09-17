package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"sort"
	"strings"
)

// WFGG_RADAR_CYCLE_QUALITY_GATE_V617
// Cluster evidence must come from a complete successful sweep. Partial sweeps
// remain useful Collector observations, but they cannot confirm a server cluster.
type cycleQualityMetaV617 struct {
	ID     int64  `json:"id"`
	Status string `json:"status"`
	Error  string `json:"error"`
	Query  string `json:"query"`
}

type cycleQualityReportV617 struct {
	OK     bool                   `json:"ok"`
	Cycles []cycleQualityMetaV617 `json:"cycles"`
}

const cycleQualityPythonV617 = `
import json, sqlite3, sys
path=sys.argv[1]
conn=sqlite3.connect('file:'+path+'?mode=ro',uri=True)
conn.row_factory=sqlite3.Row
tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if 'cycles' not in tables:
    print(json.dumps({'ok':False,'cycles':[]},separators=(',',':')))
    raise SystemExit(0)
cols={r[1] for r in conn.execute('PRAGMA table_info(cycles)')}
required={'id','status','error','query'}
if not required.issubset(cols):
    print(json.dumps({'ok':False,'cycles':[]},separators=(',',':')))
    raise SystemExit(0)
rows=[]
for r in conn.execute('SELECT id,status,COALESCE(error,\'\') error,COALESCE(query,\'\') query FROM cycles ORDER BY id'):
    rows.append({'id':int(r['id']),'status':str(r['status'] or ''),'error':str(r['error'] or ''),'query':str(r['query'] or '')})
print(json.dumps({'ok':True,'cycles':rows},separators=(',',':')))
`

func runCycleQualityMetaV617(ctx context.Context, dbPath string) (map[int64]cycleQualityMetaV617, error) {
	if strings.TrimSpace(dbPath) == "" {
		return nil, errors.New("COLLECTOR_DB_PATH_EMPTY")
	}
	if _, err := os.Stat(dbPath); err != nil {
		return nil, errors.New("CYCLE_QUALITY_DB_UNAVAILABLE")
	}
	if _, err := exec.LookPath("python3"); err != nil {
		return nil, errors.New("CYCLE_QUALITY_PYTHON3_MISSING")
	}
	cmd := exec.CommandContext(ctx, "python3", "-c", cycleQualityPythonV617, dbPath)
	out, err := cmd.Output()
	if err != nil {
		return nil, errors.New("CYCLE_QUALITY_EXEC_FAILED")
	}
	var report cycleQualityReportV617
	if err := json.Unmarshal(out, &report); err != nil || !report.OK {
		return nil, errors.New("CYCLE_QUALITY_REPORT_INVALID")
	}
	result := make(map[int64]cycleQualityMetaV617, len(report.Cycles))
	for _, row := range report.Cycles {
		result[row.ID] = row
	}
	return result, nil
}

func federatedTargetV617(query string) string {
	q := strings.TrimSpace(query)
	const prefix = "@federated:"
	if len(q) < len(prefix) || !strings.EqualFold(q[:len(prefix)], prefix) {
		return ""
	}
	return strings.TrimSpace(q[len(prefix):])
}

func cycleContainsServerV617(c serverCycleHistoryCycleV614, serverID string) bool {
	serverID = strings.TrimSpace(serverID)
	if serverID == "" {
		return false
	}
	for _, row := range c.Servers {
		if strings.TrimSpace(row.ServerID) == serverID {
			return true
		}
	}
	return false
}

func cycleEligibleForClusterV617(c serverCycleHistoryCycleV614, meta cycleQualityMetaV617, found bool) (bool, string) {
	if !found {
		return false, "CYCLE_METADATA_MISSING"
	}
	if strings.ToUpper(strings.TrimSpace(meta.Status)) != "SUCCESS" {
		return false, "CYCLE_NOT_SUCCESS"
	}
	if strings.TrimSpace(meta.Error) != "" {
		return false, "CYCLE_HAS_ERROR_MARKER"
	}
	if target := federatedTargetV617(meta.Query); target != "" && !cycleContainsServerV617(c, target) {
		// Historical recovery guard: before V6.17, region-isolated jobs were
		// persisted as SUCCESS with an empty error. A targeted sweep that does
		// not contain its own requested server is necessarily incomplete.
		return false, "FEDERATED_TARGET_MISSING"
	}
	return true, "FULL_SUCCESS"
}

func serverCycleGraphFromQualityHistoryV617(history serverCycleHistoryPayloadV614, quality map[int64]cycleQualityMetaV617) (serverCycleMapPayloadV6122, map[string]int, int, int) {
	cycles := make([]serverCycleRowV6122, 0, len(history.Cycles))
	pairCounts := map[[2]string]int{}
	serverCycles := map[string]int{}
	eligibleCount := 0
	excludedCount := 0

	for _, c := range history.Cycles {
		meta, found := quality[c.CycleID]
		eligible, _ := cycleEligibleForClusterV617(c, meta, found)
		if !eligible {
			excludedCount++
			continue
		}
		eligibleCount++
		members := append([]serverCycleMemberV6122(nil), c.Servers...)
		cycles = append(cycles, serverCycleRowV6122{CycleID: c.CycleID, ServerCount: len(members), Servers: members})

		ids := make([]string, 0, len(members))
		seen := map[string]bool{}
		for _, member := range members {
			sid := strings.TrimSpace(member.ServerID)
			if sid == "" || seen[sid] {
				continue
			}
			seen[sid] = true
			ids = append(ids, sid)
			serverCycles[sid]++
		}
		sort.Slice(ids, func(i, j int) bool { return serverIDLessV613(ids[i], ids[j]) })
		for i := 0; i < len(ids); i++ {
			for j := i + 1; j < len(ids); j++ {
				pairCounts[[2]string{ids[i], ids[j]}]++
			}
		}
	}

	edges := make([]serverPairEdgeV6122, 0, len(pairCounts))
	for pair, count := range pairCounts {
		edges = append(edges, serverPairEdgeV6122{ServerA: pair[0], ServerB: pair[1], CyclesTogether: count})
	}
	sort.Slice(edges, func(i, j int) bool {
		if edges[i].CyclesTogether != edges[j].CyclesTogether {
			return edges[i].CyclesTogether > edges[j].CyclesTogether
		}
		if edges[i].ServerA != edges[j].ServerA {
			return serverIDLessV613(edges[i].ServerA, edges[j].ServerA)
		}
		return serverIDLessV613(edges[i].ServerB, edges[j].ServerB)
	})

	return serverCycleMapPayloadV6122{
		OK:                   history.OK,
		MapVersion:           "v6.17-quality-gated",
		Readonly:             true,
		RawPlayerDataExposed: false,
		CycleCount:           len(cycles),
		EdgeCount:            len(edges),
		Cycles:               cycles,
		Edges:                edges,
	}, serverCycles, eligibleCount, excludedCount
}

func serverCensusWithQualityCyclesV617(census serverCensusPayloadV612, counts map[string]int) serverCensusPayloadV612 {
	out := census
	out.Servers = append([]serverCensusRowV612(nil), census.Servers...)
	for i := range out.Servers {
		out.Servers[i].DistinctCycles = counts[out.Servers[i].ServerID]
	}
	return out
}

func markQualityGatedCatalogV617(payload serverClusterCatalogPayloadV613) serverClusterCatalogPayloadV613 {
	payload.CatalogVersion = "v6.17"
	for i := range payload.ConfirmedClusters {
		payload.ConfirmedClusters[i].EvidenceMethod = "cycle_time_state_hash_full_success_quality_gate"
	}
	return payload
}
