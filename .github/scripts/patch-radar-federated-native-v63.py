#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go/native-template')
V3 = ROOT / 'player_scan_v3.go'
V4 = ROOT / 'player_scan_v4.go'


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# V3 decoder: keep normal exact-name/UID semantics untouched, but reserve the
# internal @all query for Federated Collector. Server Explorer still uses '*',
# so its cheap probe behaviour does not change.
# ---------------------------------------------------------------------------
s = V3.read_text(encoding='utf-8')
if 'FEDERATED_COLLECTOR_WILDCARD_V63' not in s:
    old = '''func collectMapPlayersV3(v any, query, fallbackServer, observedAt string, out *[]playerReport, seen map[string]bool, depth, area int, serverID string) {\n\tif depth > 12 || v == nil || len(*out) >= 32 {\n\t\treturn\n\t}\n'''
    new = '''func collectMapPlayersV3(v any, query, fallbackServer, observedAt string, out *[]playerReport, seen map[string]bool, depth, area int, serverID string) {\n\t// FEDERATED_COLLECTOR_WILDCARD_V63\n\tlimit := 32\n\tif strings.EqualFold(strings.TrimSpace(query), "@all") {\n\t\t// A federated map region can legitimately contain hundreds of cities.\n\t\t// Keep a hard safety ceiling while allowing Collector to build an index.\n\t\tlimit = 4096\n\t}\n\tif depth > 12 || v == nil || len(*out) >= limit {\n\t\treturn\n\t}\n'''
    s = once(s, old, new, 'federated collector player limit')

    old = '''func v3PlayerMatches(p playerReport, query string) bool {\n\tq := strings.TrimSpace(query)\n\treturn (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)\n}\n'''
    new = '''func v3PlayerMatches(p playerReport, query string) bool {\n\tq := strings.TrimSpace(query)\n\tif strings.EqualFold(q, "@all") {\n\t\treturn p.GameUID != "" && strings.TrimSpace(p.Pseudo) != ""\n\t}\n\treturn (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)\n}\n'''
    s = once(s, old, new, 'federated collector wildcard matcher')
    V3.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# V4 map engine: Federated Collector selects exactly one of the already proven
# nine origins per native invocation and skips expensive profile enrichment.
# The ordinary V4 path and WFGG_SERVER_PROBE path remain unchanged.
# ---------------------------------------------------------------------------
s = V4.read_text(encoding='utf-8')
if 'FEDERATED_COLLECTOR_NATIVE_V63' not in s:
    old = '''\tif len(players) == 0 {\n\t\treturn []playerReport{}, nil\n\t}\n\n\tfor i := range players {\n'''
    new = '''\tif len(players) == 0 {\n\t\treturn []playerReport{}, nil\n\t}\n\n\t// FEDERATED_COLLECTOR_NATIVE_V63\n\t// The global identity pass only needs map-level UID/pseudo/server/position.\n\t// Profile enrichment is a later targeted step and must not multiply the cost\n\t// of scanning hundreds of servers.\n\tif strings.TrimSpace(os.Getenv("WFGG_FEDERATED_MAP_ONLY")) == "1" {\n\t\treturn players, nil\n\t}\n\n\tfor i := range players {\n'''
    s = once(s, old, new, 'federated map-only profile bypass')

    old = '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\tprobeMode := strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) == "1"\n\tif probeMode {\n\t\t// One central origin is enough to prove that a foreign serverId produces a\n\t\t// valid map round-trip. Never turn a probe into a full server sweep.\n\t\torigins = [][2]int{{1000, 1000}}\n\t}\n'''
    new = '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\t// FEDERATED_COLLECTOR_NATIVE_V63\n\tif raw := strings.TrimSpace(os.Getenv("WFGG_FEDERATED_ORIGIN_INDEX")); raw != "" {\n\t\tidx, err := strconv.Atoi(raw)\n\t\tif err != nil || idx < 0 || idx >= len(origins) {\n\t\t\treturn nil, errors.New("FEDERATED_COLLECTOR_REGION_INVALID")\n\t\t}\n\t\torigins = [][2]int{origins[idx]}\n\t}\n\tprobeMode := strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) == "1"\n\tif probeMode {\n\t\t// One central origin is enough to prove that a foreign serverId produces a\n\t\t// valid map round-trip. Never turn a probe into a full server sweep.\n\t\torigins = [][2]int{{1000, 1000}}\n\t}\n'''
    s = once(s, old, new, 'federated origin selector')
    V4.write_text(s, encoding='utf-8')

print('FEDERATED_COLLECTOR_NATIVE_V63=PATCHED')
print('FEDERATED_COLLECTOR_QUERY=@all')
print('FEDERATED_COLLECTOR_REGION_MODE=ONE_OF_NINE_ORIGINS')
print('FEDERATED_COLLECTOR_MAP_ONLY=YES')
print('FEDERATED_COLLECTOR_SERVER_PROBE_UNCHANGED=YES')
