#!/usr/bin/env python3
from pathlib import Path

JOBS = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')
s = JOBS.read_text(encoding='utf-8')
marker = 'FEDERATED_COLLECTOR_V631_TOPOLOGY'
if marker in s:
    print('FEDERATED_COLLECTOR_V631_TOPOLOGY=ALREADY_PRESENT')
    raise SystemExit(0)


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

old = '''\tunique := map[string]protocol.Player{}\n\ttotalDecoded := 0\n\ttotalAccepted := 0\n\tregionsOK := 0\n'''
new = '''\tunique := map[string]protocol.Player{}\n\ttotalDecoded := 0\n\ttotalAccepted := 0\n\tregionsOK := 0\n\t// FEDERATED_COLLECTOR_V631_TOPOLOGY\n\t// V6.3 showed that the nine 1000x1000 origins may represent different\n\t// server tiles inside the 3000x3000 world. Record attribution per origin\n\t// before deciding how the global orchestrator should traverse servers.\n\tregionTopology := make([]map[string]any, 0, 9)\n'''
s = once(s, old, new, 'topology state')

old = '''\t\tregionsOK++\n\t\ttotalDecoded += len(players)\n\t\tfor _, p := range players {\n'''
new = '''\t\t// FEDERATED_COLLECTOR_V631_TOPOLOGY\n\t\tregionCounts := map[string]int{}\n\t\tfor _, p := range players {\n\t\t\tsid := strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS")\n\t\t\tif sid == "" { sid = "<blank>" }\n\t\t\tregionCounts[sid]++\n\t\t}\n\t\tdominantServerID := ""\n\t\tdominantCount := 0\n\t\tfor sid, count := range regionCounts {\n\t\t\tif count > dominantCount {\n\t\t\t\tdominantServerID = sid\n\t\t\t\tdominantCount = count\n\t\t\t}\n\t\t}\n\t\ttargetCount := regionCounts[serverID]\n\t\tregionTopology = append(regionTopology, map[string]any{\n\t\t\t"region": region,\n\t\t\t"decoded": len(players),\n\t\t\t"distinctServerIds": len(regionCounts),\n\t\t\t"dominantServerId": dominantServerID,\n\t\t\t"dominantCount": dominantCount,\n\t\t\t"targetCount": targetCount,\n\t\t})\n\t\tslog.Info("FEDERATED_COLLECTOR_V631_TOPOLOGY",\n\t\t\t"jobId", jobID,\n\t\t\t"serverId", serverID,\n\t\t\t"region", region,\n\t\t\t"decoded", len(players),\n\t\t\t"distinctServerIds", len(regionCounts),\n\t\t\t"dominantServerId", dominantServerID,\n\t\t\t"dominantCount", dominantCount,\n\t\t\t"targetCount", targetCount,\n\t\t)\n\n\t\tregionsOK++\n\t\ttotalDecoded += len(players)\n\t\tfor _, p := range players {\n'''
s = once(s, old, new, 'topology per-region attribution')

old = '''\t\t"serverMismatch": serverMismatch,\n\t\t"sample": sample,\n'''
new = '''\t\t"serverMismatch": serverMismatch,\n\t\t"regionTopology": regionTopology,\n\t\t"sample": sample,\n'''
s = once(s, old, new, 'topology job result')

old = '''\tslog.Info("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "DONE", "serverId", serverID, "regions", regionsOK, "decoded", totalDecoded, "uniqueUIDs", len(unique), "accepted", totalAccepted, "serverMismatch", serverMismatch)\n'''
new = '''\tslog.Info("FEDERATED_COLLECTOR_V63_SENTINEL", "jobId", jobID, "stage", "DONE", "serverId", serverID, "regions", regionsOK, "decoded", totalDecoded, "uniqueUIDs", len(unique), "accepted", totalAccepted, "serverMismatch", serverMismatch)\n\tslog.Info("FEDERATED_COLLECTOR_V631_TOPOLOGY", "jobId", jobID, "stage", "DONE", "serverId", serverID, "regions", regionsOK, "uniqueUIDs", len(unique), "targetUIDs", len(unique)-serverMismatch, "foreignUIDs", serverMismatch)\n'''
s = once(s, old, new, 'topology final sentinel')

JOBS.write_text(s, encoding='utf-8')
print('FEDERATED_COLLECTOR_V631_TOPOLOGY=PATCHED')
print('FEDERATED_COLLECTOR_V631_REGION_ATTRIBUTION=YES')
print('FEDERATED_COLLECTOR_V631_TARGET_VS_FOREIGN=YES')
