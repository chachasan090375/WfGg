#!/usr/bin/env python3
from pathlib import Path

p = Path('/tmp/wfgg-radar/connector-go/native-template/player_scan_v4.go')
s = p.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_NATIVE_V1'
if marker in s:
    print('SERVER_EXPLORER_NATIVE=ALREADY_PRESENT')
    raise SystemExit(0)

old = '''func syntheticMapSweepV4(conn net.Conn, query, fallbackServer, observedAt string) ([]playerReport, error) {\n\tserverID, err := strconv.Atoi(strings.TrimPrefix(strings.TrimSpace(fallbackServer), "APS"))\n\tif err != nil || serverID <= 0 {\n\t\treturn nil, errors.New("PLAYER_SCAN_SERVER_ID_INVALID")\n\t}\n\n\tdiag := &scanDiagV42{}\n'''
new = '''func syntheticMapSweepV4(conn net.Conn, query, fallbackServer, observedAt string) ([]playerReport, error) {\n\t// SERVER_EXPLORER_NATIVE_V1\n\t// Normal Broad Scan keeps using the authenticated session server. A dedicated\n\t// READONLY probe may override only the serverId carried by world.get.block.\n\tserverText := strings.TrimPrefix(strings.TrimSpace(fallbackServer), "APS")\n\tif override := strings.TrimSpace(os.Getenv("WFGG_SERVER_ID_OVERRIDE")); override != "" {\n\t\tserverText = strings.TrimPrefix(override, "APS")\n\t}\n\tserverID, err := strconv.Atoi(serverText)\n\tif err != nil || serverID <= 0 || serverID > 999999 {\n\t\treturn nil, errors.New("PLAYER_SCAN_SERVER_ID_INVALID")\n\t}\n\n\tdiag := &scanDiagV42{}\n'''
if s.count(old) != 1:
    raise SystemExit('SERVER_EXPLORER_NATIVE_SERVER_ANCHOR_MISSING')
s = s.replace(old, new, 1)

old = '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\n\tseen := map[string]bool{}\n\tout := make([]playerReport, 0, 4)\n\trequestID := time.Now().UnixNano() & 0x3fffffff\n\tsweepDeadline := time.Now().Add(v4SweepBudget)\n'''
new = '''\torigins := [][2]int{\n\t\t{1000, 1000},\n\t\t{0, 0}, {1000, 0}, {2000, 0},\n\t\t{0, 1000}, {2000, 1000},\n\t\t{0, 2000}, {1000, 2000}, {2000, 2000},\n\t}\n\tprobeMode := strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) == "1"\n\tif probeMode {\n\t\t// One central origin is enough to prove that a foreign serverId produces a\n\t\t// valid map round-trip. Never turn a probe into a full server sweep.\n\t\torigins = [][2]int{{1000, 1000}}\n\t}\n\n\tseen := map[string]bool{}\n\tout := make([]playerReport, 0, 4)\n\trequestID := time.Now().UnixNano() & 0x3fffffff\n\tsweepBudget := v4SweepBudget\n\tif probeMode {\n\t\tsweepBudget = 1100 * time.Millisecond\n\t}\n\tsweepDeadline := time.Now().Add(sweepBudget)\n'''
if s.count(old) != 1:
    raise SystemExit('SERVER_EXPLORER_NATIVE_ORIGIN_ANCHOR_MISSING')
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('SERVER_EXPLORER_NATIVE=PATCHED')
print('SERVER_EXPLORER_NATIVE_MODE=READONLY_WORLD_GET_BLOCK')
print('SERVER_EXPLORER_NATIVE_PROBE_BUDGET_MS=1100')
