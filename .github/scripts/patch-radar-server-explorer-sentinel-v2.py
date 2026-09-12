#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar/connector-go')
MAIN = ROOT / 'native-template/main.go'
V4 = ROOT / 'native-template/player_scan_v4.go'
REGION = ROOT / 'internal/protocol/region_scan.go'


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Native process: emit only safe stage names while Server Explorer probe mode
# is active. No token, UID, pseudo, coordinates or player data are logged.
# ---------------------------------------------------------------------------
s = MAIN.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_NATIVE_SENTINEL_V2' not in s:
    anchor = 'var shieldKeys = keySet("shield", "shieldstate", "shield_state", "shieldstatus", "shield_status")\n'
    helper = anchor + '''\n// SERVER_EXPLORER_NATIVE_SENTINEL_V2\nfunc serverExplorerNativeSentinel(stage string) {\n\tif strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) != "1" {\n\t\treturn\n\t}\n\t_, _ = os.Stderr.WriteString("SERVER_EXPLORER_NATIVE_SENTINEL stage=" + stage + "\\n")\n}\n'''
    s = replace_once(s, anchor, helper, 'native sentinel helper')

    s = replace_once(s,
        '''\tpackets, err := pcap.Parse(data)\n\tif err != nil {\n\t\tfail("CAPTURE_PARSE_FAILED", err)\n\t}\n\tconvs := pcap.Conversations(packets)\n''',
        '''\tpackets, err := pcap.Parse(data)\n\tif err != nil {\n\t\tfail("CAPTURE_PARSE_FAILED", err)\n\t}\n\tconvs := pcap.Conversations(packets)\n\tserverExplorerNativeSentinel("PCAP_READY")\n''',
        'pcap stage')

    s = replace_once(s,
        '''\tconn, err := net.DialTimeout("tcp", server.String(), 10*time.Second)\n''',
        '''\tserverExplorerNativeSentinel("DIAL_START")\n\tconn, err := net.DialTimeout("tcp", server.String(), 10*time.Second)\n''',
        'dial start stage')

    s = replace_once(s,
        '''\tdefer conn.Close()\n\t_ = conn.SetDeadline(time.Now().Add(25 * time.Second))\n''',
        '''\tdefer conn.Close()\n\tserverExplorerNativeSentinel("DIAL_OK")\n\t_ = conn.SetDeadline(time.Now().Add(25 * time.Second))\n''',
        'dial ok stage')

    s = replace_once(s,
        '''\tif _, err := conn.Write(frame); err != nil {\n\t\tfailWith(base, "LOGIN_WRITE_FAILED", err)\n\t}\n''',
        '''\tif _, err := conn.Write(frame); err != nil {\n\t\tfailWith(base, "LOGIN_WRITE_FAILED", err)\n\t}\n\tserverExplorerNativeSentinel("LOGIN_SENT")\n''',
        'login sent stage')

    s = replace_once(s,
        '''\t\t\tbase.LoginResponse = "OK"\n\t\t\tloginOK = true\n\t\t\tcontinue\n''',
        '''\t\t\tbase.LoginResponse = "OK"\n\t\t\tloginOK = true\n\t\t\tserverExplorerNativeSentinel("LOGIN_OK")\n\t\t\tcontinue\n''',
        'login ok stage')

    s = replace_once(s,
        '''\t\t\tbase.OK = true\n\t\t\tbase.InitReceived = true\n''',
        '''\t\t\tbase.OK = true\n\t\t\tbase.InitReceived = true\n\t\t\tserverExplorerNativeSentinel("INIT_OK")\n''',
        'init ok stage')

    s = replace_once(s,
        '''\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n''',
        '''\tserverExplorerNativeSentinel("MAP_DISPATCH")\n\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n\tserverExplorerNativeSentinel("MAP_RETURN")\n''',
        'map dispatch stage')

    MAIN.write_text(s, encoding='utf-8')

s = V4.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_MAP_SENTINEL_V2' not in s:
    s = replace_once(s,
        '''func syntheticMapSweepV4(conn net.Conn, query, fallbackServer, observedAt string) ([]playerReport, error) {\n''',
        '''func syntheticMapSweepV4(conn net.Conn, query, fallbackServer, observedAt string) ([]playerReport, error) {\n\t// SERVER_EXPLORER_MAP_SENTINEL_V2\n\tserverExplorerNativeSentinel("SYNTHETIC_START")\n''',
        'synthetic start stage')
    s = replace_once(s,
        '''\t\t\t\tif _, err := conn.Write(frame); err != nil {\n''',
        '''\t\t\t\tif _, err := conn.Write(frame); err != nil {\n''',
        'synthetic write anchor validation')
    # Place a single safe marker after the first successful world.get.block write.
    s = replace_once(s,
        '''\tseen := map[string]bool{}\n\tout := make([]playerReport, 0, 4)\n''',
        '''\tseen := map[string]bool{}\n\tout := make([]playerReport, 0, 4)\n\twriteMarked := false\n\tpacketMarked := false\n''',
        'synthetic marker flags')
    s = replace_once(s,
        '''\t\t\t\tdiag.Requests++\n\t\t\t\twritesThisOrigin++\n''',
        '''\t\t\t\tdiag.Requests++\n\t\t\t\twritesThisOrigin++\n\t\t\t\tif !writeMarked {\n\t\t\t\t\tserverExplorerNativeSentinel("MAP_WRITE_OK")\n\t\t\t\t\twriteMarked = true\n\t\t\t\t}\n''',
        'map write stage')
    s = replace_once(s,
        '''\t\t\tdiag.Packets++\n\t\t\tobj, err := sfs.DecodeObject(rb)\n''',
        '''\t\t\tdiag.Packets++\n\t\t\tif !packetMarked {\n\t\t\t\tserverExplorerNativeSentinel("MAP_PACKET_RX")\n\t\t\t\tpacketMarked = true\n\t\t\t}\n\t\t\tobj, err := sfs.DecodeObject(rb)\n''',
        'map packet stage')
    V4.write_text(s, encoding='utf-8')

# ---------------------------------------------------------------------------
# Connector: when the parent budget kills the native process, preserve the
# last safe stage emitted by the child so Sentinel can identify the bottleneck.
# ---------------------------------------------------------------------------
s = REGION.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_PROTOCOL_SENTINEL_V2' not in s:
    anchor = '''func profileProtocolSentinel(stage string, rep nativeTemplateReport, runErr error, stdoutBytes, stderrBytes int) {\n'''
    helper = '''// SERVER_EXPLORER_PROTOCOL_SENTINEL_V2\nfunc lastServerExplorerNativeStage(raw []byte) string {\n\tconst prefix = "SERVER_EXPLORER_NATIVE_SENTINEL stage="\n\tlast := "NO_STAGE"\n\tfor _, line := range strings.Split(string(raw), "\\n") {\n\t\tline = strings.TrimSpace(line)\n\t\tif !strings.HasPrefix(line, prefix) {\n\t\t\tcontinue\n\t\t}\n\t\tstage := safeNativeCode(strings.TrimSpace(strings.TrimPrefix(line, prefix)))\n\t\tif stage != "EMPTY" {\n\t\t\tlast = stage\n\t\t}\n\t}\n\treturn last\n}\n\n'''
    if s.count(anchor) != 1:
        raise SystemExit('protocol sentinel helper anchor missing')
    s = s.replace(anchor, helper + anchor, 1)

    s = replace_once(s,
        '''\trunErr := cmd.Run()\n\tif ctx.Err() != nil {\n\t\tif profileMode {\n''',
        '''\tstartedAt := time.Now()\n\trunErr := cmd.Run()\n\tdurationMs := time.Since(startedAt).Milliseconds()\n\tif ctx.Err() != nil {\n\t\tif serverIDOverride != "" {\n\t\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL",\n\t\t\t\t"stage", "NATIVE_TIMEOUT",\n\t\t\t\t"serverId", serverIDOverride,\n\t\t\t\t"nativeStage", lastServerExplorerNativeStage(stderr.Bytes()),\n\t\t\t\t"durationMs", durationMs,\n\t\t\t\t"stdoutBytes", len(stdout.Bytes()),\n\t\t\t\t"stderrBytes", len(stderr.Bytes()),\n\t\t\t)\n\t\t}\n\t\tif profileMode {\n''',
        'timeout stage preservation')

    s = replace_once(s,
        '''\tvar rep nativeTemplateReport\n''',
        '''\tif serverIDOverride != "" {\n\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL",\n\t\t\t"stage", "NATIVE_RETURN",\n\t\t\t"serverId", serverIDOverride,\n\t\t\t"nativeStage", lastServerExplorerNativeStage(stderr.Bytes()),\n\t\t\t"durationMs", durationMs,\n\t\t\t"runError", runErr != nil,\n\t\t\t"stdoutBytes", len(stdout.Bytes()),\n\t\t\t"stderrBytes", len(stderr.Bytes()),\n\t\t)\n\t}\n\n\tvar rep nativeTemplateReport\n''',
        'normal return stage preservation')

    REGION.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_SENTINEL_V2=PATCHED')
print('SERVER_EXPLORER_SENTINEL_V2_DATA=SAFE_STAGE_ONLY')
print('SERVER_EXPLORER_SENTINEL_V2_TIMEOUT_TRACE=READY')
