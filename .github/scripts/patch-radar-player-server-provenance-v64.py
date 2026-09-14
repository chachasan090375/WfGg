#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
PROTO = ROOT / 'internal/protocol/protocol.go'
JOBS = ROOT / 'cmd/radar-connector/collector_jobs.go'


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Protocol: do not overload serverId with two different meanings.
# serverId              = current map server observed by a world.get.block scan
# rawServerId           = raw/inherited Last War value before interpretation
# observedOnServerId    = explicit server targeted by the map request
# serverIdSource        = machine-readable source of the interpreted serverId
# serverProvenance      = OBSERVED / INFERRED / PROVEN / INVALIDATED vocabulary
# ---------------------------------------------------------------------------
s = PROTO.read_text(encoding='utf-8')
if 'PLAYER_SERVER_PROVENANCE_V64' not in s:
    old = '''type Player struct {\n\tGameUID     string `json:"gameUid,omitempty"`\n\tPseudo      string `json:"pseudo,omitempty"`\n\tServerID    string `json:"serverId,omitempty"`\n\tAllianceID  string `json:"allianceId,omitempty"`\n'''
    new = '''type Player struct {\n\tGameUID            string `json:"gameUid,omitempty"`\n\tPseudo             string `json:"pseudo,omitempty"`\n\tServerID           string `json:"serverId,omitempty"`\n\tRawServerID        string `json:"rawServerId,omitempty"`\n\tObservedOnServerID string `json:"observedOnServerId,omitempty"`\n\tServerIDSource     string `json:"serverIdSource,omitempty"`\n\tServerProvenance   string `json:"serverProvenance,omitempty"` // PLAYER_SERVER_PROVENANCE_V64\n\tAllianceID         string `json:"allianceId,omitempty"`\n'''
    s = once(s, old, new, 'protocol player provenance fields')
    PROTO.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Federated Collector: world.get.block is sent to an explicit serverId. A base
# decoded from that response is therefore OBSERVED on that requested map. The
# nested/inherited serverId found inside a player/map blob is retained as RAW
# evidence only; it must not silently overwrite the current physical map server.
# ---------------------------------------------------------------------------
s = JOBS.read_text(encoding='utf-8')
if 'PLAYER_SERVER_PROVENANCE_V64' not in s:
    old = '''\t\t// FEDERATED_COLLECTOR_V631_TOPOLOGY\n\t\tregionCounts := map[string]int{}\n\t\tfor _, p := range players {\n\t\t\tsid := strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS")\n\t\t\tif sid == "" { sid = "<blank>" }\n\t\t\tregionCounts[sid]++\n\t\t}\n'''
    new = '''\t\t// PLAYER_SERVER_PROVENANCE_V64\n\t\t// Normalize attribution before ingestion. The explicit federated target is\n\t\t// the observed map server. Preserve the decoder's previous value separately\n\t\t// because it may be account-origin, enclosing-response context, or another\n\t\t// Last War semantic that has not yet been proven.\n\t\tfor i := range players {\n\t\t\traw := strings.TrimPrefix(strings.TrimSpace(players[i].ServerID), "APS")\n\t\t\tplayers[i].RawServerID = raw\n\t\t\tplayers[i].ObservedOnServerID = serverID\n\t\t\tplayers[i].ServerID = serverID\n\t\t\tplayers[i].ServerIDSource = "WORLD_GET_BLOCK_TARGET"\n\t\t\tplayers[i].ServerProvenance = "OBSERVED"\n\t\t}\n\n\t\t// Keep topology diagnostics on RAW values only. They are evidence for\n\t\t// cluster/origin analysis, never proof of current base location.\n\t\tregionCounts := map[string]int{}\n\t\tfor _, p := range players {\n\t\t\tsid := strings.TrimPrefix(strings.TrimSpace(p.RawServerID), "APS")\n\t\t\tif sid == "" { sid = "<blank>" }\n\t\t\tregionCounts[sid]++\n\t\t}\n'''
    s = once(s, old, new, 'federated attribution normalization')

    old = '''\t\tregionTopology = append(regionTopology, map[string]any{\n\t\t\t"region": region,\n\t\t\t"decoded": len(players),\n\t\t\t"distinctServerIds": len(regionCounts),\n\t\t\t"dominantServerId": dominantServerID,\n\t\t\t"dominantCount": dominantCount,\n\t\t\t"targetCount": targetCount,\n\t\t})\n'''
    new = '''\t\tregionTopology = append(regionTopology, map[string]any{\n\t\t\t"region": region,\n\t\t\t"decoded": len(players),\n\t\t\t"rawDistinctServerIds": len(regionCounts),\n\t\t\t"rawDominantServerId": dominantServerID,\n\t\t\t"rawDominantCount": dominantCount,\n\t\t\t"rawTargetCount": targetCount,\n\t\t\t"rawSemantics": "UNCLASSIFIED",\n\t\t\t"observedOnServerId": serverID,\n\t\t\t"serverProvenance": "OBSERVED",\n\t\t})\n'''
    s = once(s, old, new, 'topology provenance payload')

    old = '''\t\tregionsOK++\n\t\ttotalDecoded += len(players)\n\t\tfor _, p := range players {\n\t\t\tuid := strings.TrimSpace(p.GameUID)\n\t\t\tif uid == "" || strings.TrimSpace(p.Pseudo) == "" {\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tif p.ServerID == "" {\n\t\t\t\tp.ServerID = serverID\n\t\t\t}\n\t\t\tunique[uid] = p\n\t\t}\n'''
    new = '''\t\tregionsOK++\n\t\ttotalDecoded += len(players)\n\t\tfor _, p := range players {\n\t\t\tuid := strings.TrimSpace(p.GameUID)\n\t\t\tif uid == "" || strings.TrimSpace(p.Pseudo) == "" {\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tunique[uid] = p\n\t\t}\n'''
    s = once(s, old, new, 'remove ambiguous server fallback')

    old = '''\tsample := make([]map[string]any, 0, 8)\n\tserverMismatch := 0\n\tfor _, p := range unique {\n\t\tif strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS") != serverID {\n\t\t\tserverMismatch++\n\t\t}\n\t\tif len(sample) < 8 {\n\t\t\titem := map[string]any{\n\t\t\t\t"uid": p.GameUID,\n\t\t\t\t"pseudo": p.Pseudo,\n\t\t\t\t"serverId": p.ServerID,\n\t\t\t}\n'''
    new = '''\tsample := make([]map[string]any, 0, 8)\n\tserverMismatch := 0\n\trawServerMismatch := 0\n\tfor _, p := range unique {\n\t\tif strings.TrimPrefix(strings.TrimSpace(p.ServerID), "APS") != serverID {\n\t\t\tserverMismatch++\n\t\t}\n\t\traw := strings.TrimPrefix(strings.TrimSpace(p.RawServerID), "APS")\n\t\tif raw != "" && raw != serverID {\n\t\t\trawServerMismatch++\n\t\t}\n\t\tif len(sample) < 8 {\n\t\t\titem := map[string]any{\n\t\t\t\t"uid": p.GameUID,\n\t\t\t\t"pseudo": p.Pseudo,\n\t\t\t\t"serverId": p.ServerID,\n\t\t\t\t"rawServerId": p.RawServerID,\n\t\t\t\t"observedOnServerId": p.ObservedOnServerID,\n\t\t\t\t"serverIdSource": p.ServerIDSource,\n\t\t\t\t"serverProvenance": p.ServerProvenance,\n\t\t\t}\n'''
    s = once(s, old, new, 'canary raw versus observed sample')

    old = '''\t\t"serverMismatch": serverMismatch,\n\t\t"regionTopology": regionTopology,\n\t\t"sample": sample,\n'''
    new = '''\t\t"serverMismatch": serverMismatch,\n\t\t"rawServerMismatch": rawServerMismatch,\n\t\t"serverAttribution": "WORLD_GET_BLOCK_TARGET",\n\t\t"serverProvenance": "OBSERVED",\n\t\t"rawServerSemantics": "UNCLASSIFIED",\n\t\t"regionTopology": regionTopology,\n\t\t"sample": sample,\n'''
    s = once(s, old, new, 'canary provenance result')

    old = '''\tslog.Info("FEDERATED_COLLECTOR_V631_TOPOLOGY", "jobId", jobID, "stage", "DONE", "serverId", serverID, "regions", regionsOK, "uniqueUIDs", len(unique), "targetUIDs", len(unique)-serverMismatch, "foreignUIDs", serverMismatch)\n'''
    new = '''\tslog.Info("PLAYER_SERVER_PROVENANCE_V64", "jobId", jobID, "stage", "DONE", "observedOnServerId", serverID, "regions", regionsOK, "uniqueUIDs", len(unique), "serverMismatch", serverMismatch, "rawServerMismatch", rawServerMismatch, "rawSemantics", "UNCLASSIFIED")\n'''
    s = once(s, old, new, 'replace misleading foreign topology conclusion')

    JOBS.write_text(s, encoding='utf-8')

print('PLAYER_SERVER_PROVENANCE_V64=PATCHED')
print('CURRENT_SERVER_SOURCE=WORLD_GET_BLOCK_TARGET')
print('RAW_SERVER_SEMANTICS=UNCLASSIFIED')
print('SERVER_PROVENANCE=OBSERVED')
print('MANUAL_PLAYER_CHECK_REQUIRED=NO')
