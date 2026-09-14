#!/usr/bin/env python3
from pathlib import Path

REGION = Path('/tmp/wfgg-radar/connector-go/internal/protocol/region_scan.go')


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

s = REGION.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_PROTOCOL_SUMMARY_V4' not in s:
    anchor = '''func lastServerExplorerNativeStage(raw []byte) string {\n\tconst prefix = "SERVER_EXPLORER_NATIVE_SENTINEL stage="\n\tlast := "NO_STAGE"\n\tfor _, line := range strings.Split(string(raw), "\\n") {\n\t\tline = strings.TrimSpace(line)\n\t\tif !strings.HasPrefix(line, prefix) {\n\t\t\tcontinue\n\t\t}\n\t\tstage := safeNativeCode(strings.TrimSpace(strings.TrimPrefix(line, prefix)))\n\t\tif stage != "EMPTY" {\n\t\t\tlast = stage\n\t\t}\n\t}\n\treturn last\n}\n\n'''
    helper = anchor + '''// SERVER_EXPLORER_PROTOCOL_SUMMARY_V4\nfunc serverExplorerNativeStageSeen(raw []byte, wanted string) bool {\n\tneedle := "SERVER_EXPLORER_NATIVE_SENTINEL stage=" + wanted\n\tfor _, line := range strings.Split(string(raw), "\\n") {\n\t\tif strings.TrimSpace(line) == needle {\n\t\t\treturn true\n\t\t}\n\t}\n\treturn false\n}\n\n'''
    s = replace_once(s, anchor, helper, 'summary helper')

    old_timeout = '''\t\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL", "stage", "NATIVE_TIMEOUT", "serverId", serverIDOverride, "nativeStage", lastServerExplorerNativeStage(stderr.Bytes()), "durationMs", durationMs, "stdoutBytes", len(stdout.Bytes()), "stderrBytes", len(stderr.Bytes()))\n'''
    new_timeout = '''\t\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL", "stage", "NATIVE_TIMEOUT", "serverId", serverIDOverride, "nativeStage", lastServerExplorerNativeStage(stderr.Bytes()), "durationMs", durationMs, "stdoutBytes", len(stdout.Bytes()), "stderrBytes", len(stderr.Bytes()), "initWaitPhase1", serverExplorerNativeStageSeen(stderr.Bytes(), "INIT_WAIT_PHASE1"), "loginInitSent", serverExplorerNativeStageSeen(stderr.Bytes(), "LOGIN_INIT_PULL_SENT"), "postLoginPacket", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_PACKET_RX"), "postLoginDecodeOK", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_DECODE_OK"), "postLoginDecodeFail", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_DECODE_FAIL"), "postLoginOtherExtension", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_EXTENSION_OTHER"), "initOK", serverExplorerNativeStageSeen(stderr.Bytes(), "INIT_OK"), "mapPacket", serverExplorerNativeStageSeen(stderr.Bytes(), "MAP_PACKET_RX"))\n'''
    s = replace_once(s, old_timeout, new_timeout, 'timeout summary')

    old_return = '''\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL", "stage", "NATIVE_RETURN", "serverId", serverIDOverride, "nativeStage", lastServerExplorerNativeStage(stderr.Bytes()), "durationMs", durationMs, "runError", runErr != nil, "stdoutBytes", len(stdout.Bytes()), "stderrBytes", len(stderr.Bytes()))\n'''
    new_return = '''\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL", "stage", "NATIVE_RETURN", "serverId", serverIDOverride, "nativeStage", lastServerExplorerNativeStage(stderr.Bytes()), "durationMs", durationMs, "runError", runErr != nil, "stdoutBytes", len(stdout.Bytes()), "stderrBytes", len(stderr.Bytes()), "initWaitPhase1", serverExplorerNativeStageSeen(stderr.Bytes(), "INIT_WAIT_PHASE1"), "loginInitSent", serverExplorerNativeStageSeen(stderr.Bytes(), "LOGIN_INIT_PULL_SENT"), "postLoginPacket", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_PACKET_RX"), "postLoginDecodeOK", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_DECODE_OK"), "postLoginDecodeFail", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_DECODE_FAIL"), "postLoginOtherExtension", serverExplorerNativeStageSeen(stderr.Bytes(), "POST_LOGIN_EXTENSION_OTHER"), "initOK", serverExplorerNativeStageSeen(stderr.Bytes(), "INIT_OK"), "mapPacket", serverExplorerNativeStageSeen(stderr.Bytes(), "MAP_PACKET_RX"))\n'''
    s = replace_once(s, old_return, new_return, 'return summary')

    REGION.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_PROTOCOL_SUMMARY_V4=PATCHED')
print('SERVER_EXPLORER_PROTOCOL_SUMMARY_V4_DATA=SAFE_STAGE_BOOLEANS_ONLY')
