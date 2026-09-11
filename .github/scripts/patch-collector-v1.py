#!/usr/bin/env python3
from pathlib import Path

V3 = Path('/tmp/wfgg-radar/connector-go/native-template/player_scan_v3.go')
V4 = Path('/tmp/wfgg-radar/connector-go/native-template/player_scan_v4.go')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old, new, 1)


# Collector-only V3 behaviour: wildcard means "cache every player base", and the
# per-run cap is raised because Collector ingests in batches on the VPS.
v3 = V3.read_text(encoding='utf-8')
v3 = replace_once(
    v3,
    'if depth > 12 || v == nil || len(*out) >= 32 {',
    'if depth > 12 || v == nil || len(*out) >= 50000 {',
    'collector player cap',
)
v3 = replace_once(
    v3,
    '''func v3PlayerMatches(p playerReport, query string) bool {\n\tq := strings.TrimSpace(query)\n\treturn (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)\n}\n''',
    '''func v3PlayerMatches(p playerReport, query string) bool {\n\tq := strings.TrimSpace(query)\n\tif q == "*" {\n\t\treturn p.GameUID != "" && strings.TrimSpace(p.Pseudo) != ""\n\t}\n\treturn (p.GameUID != "" && p.GameUID == q) || strings.EqualFold(strings.TrimSpace(p.Pseudo), q)\n}\n''',
    'collector wildcard match',
)
V3.write_text(v3, encoding='utf-8')

v4 = V4.read_text(encoding='utf-8')

# Keep a valid map hit even if optional profile enrichment fails.
v4 = replace_once(
    v4,
    '''\t\tif profileTemplate != nil {\n\t\t\tp, ok, err := requestProfileV3(conn, profileTemplate, players[i].GameUID, observedAt)\n\t\t\tif err != nil {\n\t\t\t\treturn nil, err\n\t\t\t}\n\t\t\tif ok {\n\t\t\t\tmergePlayerProfileV3(&players[i], p)\n\t\t\t}\n\t\t}\n''',
    '''\t\tif profileTemplate != nil {\n\t\t\tp, ok, err := requestProfileV3(conn, profileTemplate, players[i].GameUID, observedAt)\n\t\t\tif err != nil {\n\t\t\t\t// Collector keeps a valid map hit even when optional profile\n\t\t\t\t// enrichment is unavailable or times out.\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tif ok {\n\t\t\t\tmergePlayerProfileV3(&players[i], p)\n\t\t\t}\n\t\t}\n''',
    'collector profile best effort',
)

# A wildcard full-map pass stores map data only. Profile enrichment is a later,
# separate batch stage and must not turn a discovery pass into thousands of calls.
v4 = replace_once(
    v4,
    '''\tif len(players) == 0 {\n\t\treturn []playerReport{}, nil\n\t}\n\n\tfor i := range players {\n''',
    '''\tif len(players) == 0 {\n\t\treturn []playerReport{}, nil\n\t}\n\tif query == "*" {\n\t\treturn players, nil\n\t}\n\n\tfor i := range players {\n''',
    'collector wildcard skips profile stage',
)

# Diagnostics must follow the proven player-base mapping (f2=6, nested detail f3).
v4 = replace_once(
    v4,
    '\t\tdetailRaw, ok := protoBytesV3(m, 10)\n',
    '\t\tdetailRaw, ok := protoBytesV3(m, 3)\n',
    'collector diagnostic detail field',
)

# One Collector process scans one 1000x1000 origin. The supervisor reconnects for
# the next origin, avoiding the server-side connection lifetime seen in testing.
v4 = replace_once(
    v4,
    '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n''',
    '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\tif raw := strings.TrimSpace(os.Getenv("WFGG_COLLECTOR_ORIGIN_INDEX")); raw != "" {\n\t\ti, err := strconv.Atoi(raw)\n\t\tif err != nil || i < 0 || i >= len(origins) {\n\t\t\treturn nil, errors.New("PLAYER_SCAN_ORIGIN_INDEX_INVALID")\n\t\t}\n\t\torigins = origins[i : i+1]\n\t}\n''',
    'collector origin selector',
)

# For wildcard collection, continue reading the whole selected origin rather than
# returning on the first player packet.
v4 = replace_once(
    v4,
    '''\t\t\tcollectMapPlayersV3(obj, query, fallbackServer, observedAt, &out, seen, 0, 1000, fallbackServer)\n\t\t\tif len(out) > 0 {\n\t\t\t\treturn out, nil\n\t\t\t}\n''',
    '''\t\t\tcollectMapPlayersV3(obj, query, fallbackServer, observedAt, &out, seen, 0, 1000, fallbackServer)\n\t\t\tif query != "*" && len(out) > 0 {\n\t\t\t\treturn out, nil\n\t\t\t}\n''',
    'collector wildcard keeps reading',
)

# If Last War closes a Collector discovery connection after useful packets were
# received, preserve the collected rows instead of discarding the whole origin.
v4 = replace_once(
    v4,
    '''\t\t\trb, err := sfs.ReadPacket(conn)\n\t\t\tif err != nil {\n\t\t\t\tif isTimeoutV4(err) {\n\t\t\t\t\tdiag.ReadTimeouts++\n\t\t\t\t\tbreak\n\t\t\t\t}\n\t\t\t\treturn nil, fmt.Errorf("PLAYER_SCAN_SYNTHETIC_READ_FAILED:%T:%v:origin=%d,%d:writes=%d:reads=%d", err, err, ox, oy, writesThisOrigin, i)\n\t\t\t}\n''',
    '''\t\t\trb, err := sfs.ReadPacket(conn)\n\t\t\tif err != nil {\n\t\t\t\tif isTimeoutV4(err) {\n\t\t\t\t\tdiag.ReadTimeouts++\n\t\t\t\t\tbreak\n\t\t\t\t}\n\t\t\t\tif query == "*" && len(out) > 0 {\n\t\t\t\t\treturn out, nil\n\t\t\t\t}\n\t\t\t\treturn nil, fmt.Errorf("PLAYER_SCAN_SYNTHETIC_READ_FAILED:%T:%v:origin=%d,%d:writes=%d:reads=%d", err, err, ox, oy, writesThisOrigin, i)\n\t\t\t}\n''',
    'collector partial success on read close',
)

V4.write_text(v4, encoding='utf-8')

print('COLLECTOR_V1_PROFILE_ENRICHMENT=BEST_EFFORT')
print('COLLECTOR_V11_WILDCARD=ALL_PLAYERS')
print('COLLECTOR_V11_REGION_MODE=RESUMABLE_9_ORIGINS')
print('COLLECTOR_V11_PARTIAL_SUCCESS=YES')
