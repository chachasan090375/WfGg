#!/usr/bin/env python3
from pathlib import Path

REGION = Path('/tmp/wfgg-radar/connector-go/internal/protocol/region_scan.go')


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

s = REGION.read_text(encoding='utf-8')
if 'SERVER_EXPLORER_PROTOCOL_SENTINEL_V2' not in s:
    anchor = 'func profileProtocolSentinel(stage string, rep nativeTemplateReport, runErr error, stdoutBytes, stderrBytes int) {\n'
    helper = '''// SERVER_EXPLORER_PROTOCOL_SENTINEL_V2\nfunc lastServerExplorerNativeStage(raw []byte) string {\n\tconst prefix = "SERVER_EXPLORER_NATIVE_SENTINEL stage="\n\tlast := "NO_STAGE"\n\tfor _, line := range strings.Split(string(raw), "\\n") {\n\t\tline = strings.TrimSpace(line)\n\t\tif !strings.HasPrefix(line, prefix) {\n\t\t\tcontinue\n\t\t}\n\t\tstage := safeNativeCode(strings.TrimSpace(strings.TrimPrefix(line, prefix)))\n\t\tif stage != "EMPTY" {\n\t\t\tlast = stage\n\t\t}\n\t}\n\treturn last\n}\n\n'''
    if s.count(anchor) != 1:
        raise SystemExit('protocol helper anchor missing')
    s = s.replace(anchor, helper + anchor, 1)

    s = replace_once(s,
        '\trunErr := cmd.Run()\n\tif ctx.Err() != nil {\n\t\tif profileMode {\n',
        '\tstartedAt := time.Now()\n\trunErr := cmd.Run()\n\tdurationMs := time.Since(startedAt).Milliseconds()\n\tif ctx.Err() != nil {\n\t\tif serverIDOverride != "" {\n\t\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL", "stage", "NATIVE_TIMEOUT", "serverId", serverIDOverride, "nativeStage", lastServerExplorerNativeStage(stderr.Bytes()), "durationMs", durationMs, "stdoutBytes", len(stdout.Bytes()), "stderrBytes", len(stderr.Bytes()))\n\t\t}\n\t\tif profileMode {\n',
        'timeout preservation')

    s = replace_once(s,
        '\tvar rep nativeTemplateReport\n',
        '\tif serverIDOverride != "" {\n\t\tslog.Info("SERVER_EXPLORER_PROTOCOL_SENTINEL", "stage", "NATIVE_RETURN", "serverId", serverIDOverride, "nativeStage", lastServerExplorerNativeStage(stderr.Bytes()), "durationMs", durationMs, "runError", runErr != nil, "stdoutBytes", len(stdout.Bytes()), "stderrBytes", len(stderr.Bytes()))\n\t}\n\n\tvar rep nativeTemplateReport\n',
        'return preservation')

    REGION.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_PROTOCOL_SENTINEL_V2=PATCHED')
print('SERVER_EXPLORER_PROTOCOL_SENTINEL_V2_TIMEOUT_TRACE=READY')
