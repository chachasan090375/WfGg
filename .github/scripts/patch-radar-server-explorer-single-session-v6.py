#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/native-template/main.go')


def once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

s = MAIN.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_SINGLE_SESSION_V6' not in s:
    report_anchor = '\tPlayers           []playerReport `json:"players,omitempty"`\n\tErrorCode         any            `json:"errorCode,omitempty"`\n'
    report_new = '\tPlayers           []playerReport `json:"players,omitempty"`\n\tServerProbe       []serverProbeV6 `json:"serverProbe,omitempty"`\n\tErrorCode         any            `json:"errorCode,omitempty"`\n'
    s = once(s, report_anchor, report_new, 'report field')

    helper_anchor = 'var dynamicKeys = map[string]bool{\n'
    helper = r'''// SERVER_EXPLORER_SINGLE_SESSION_V6
type serverProbeV6 struct {
	ServerID        string `json:"serverId"`
	Accessible      bool   `json:"accessible"`
	PlayersObserved int    `json:"playersObserved"`
	DurationMs      int64  `json:"durationMs"`
	Error           string `json:"error,omitempty"`
}

func parseServerBatchV6(raw string) ([]string, bool) {
	parts := strings.Split(raw, ",")
	if len(parts) == 0 || len(parts) > 12 {
		return nil, false
	}
	out := make([]string, 0, len(parts))
	seen := map[string]bool{}
	for _, part := range parts {
		part = strings.TrimPrefix(strings.TrimSpace(part), "APS")
		n, err := strconv.Atoi(part)
		if err != nil || n <= 0 || n > 999999 {
			return nil, false
		}
		part = strconv.Itoa(n)
		if !seen[part] {
			seen[part] = true
			out = append(out, part)
		}
	}
	return out, len(out) > 0
}

'''
    s = once(s, helper_anchor, helper + helper_anchor, 'batch helper')

    dispatch_anchor = '''\tserverExplorerNativeSentinel("MAP_DISPATCH")\n\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n'''
    dispatch_new = '''\tif rawBatch := strings.TrimSpace(os.Getenv("WFGG_SERVER_ID_LIST")); rawBatch != "" {\n\t\tids, ok := parseServerBatchV6(rawBatch)\n\t\tif !ok {\n\t\t\tbase.OK = false\n\t\t\tbase.LoginResponse = "SERVER_EXPLORER_BATCH_INVALID"\n\t\t\temit(base)\n\t\t\tos.Exit(8)\n\t\t}\n\t\tserverExplorerNativeSentinel("V6_BATCH_START")\n\t\trows := make([]serverProbeV6, 0, len(ids))\n\t\tfor _, sid := range ids {\n\t\t\tstarted := time.Now()\n\t\t\tplayers, probeErr := runPlayerScanV4(conn, nil, server, nil, nil, "*", sid)\n\t\t\trow := serverProbeV6{ServerID: sid, PlayersObserved: len(players), DurationMs: time.Since(started).Milliseconds()}\n\t\t\tif probeErr == nil {\n\t\t\t\trow.Accessible = true\n\t\t\t} else {\n\t\t\t\trow.Error = "MAP_PROBE_FAILED"\n\t\t\t}\n\t\t\trows = append(rows, row)\n\t\t}\n\t\tbase.ServerProbe = rows\n\t\tbase.OK = true\n\t\tbase.LoginResponse = "OK"\n\t\tbase.ScanTemplateFound = true\n\t\tbase.ScanPerformed = true\n\t\tbase.ScanCommand = "world.get.block(batch-v6)"\n\t\tserverExplorerNativeSentinel("V6_BATCH_DONE")\n\t\temit(base)\n\t\treturn\n\t}\n\n\tserverExplorerNativeSentinel("MAP_DISPATCH")\n\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n'''
    s = once(s, dispatch_anchor, dispatch_new, 'batch dispatch')
    MAIN.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_SINGLE_SESSION_V6=PATCHED')
print('SERVER_EXPLORER_V6_MAX_BATCH=12')
print('SERVER_EXPLORER_V6_REUSES_ONE_LOGIN_INIT=YES')
