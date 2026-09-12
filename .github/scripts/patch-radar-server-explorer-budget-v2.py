#!/usr/bin/env python3
from pathlib import Path

JOBS = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')

s = JOBS.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_CONTROL_BUDGET_V3'
if marker not in s:
    old = '''\t\tprobeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)\n\t\tplayers, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)\n'''
    new = '''\t\t// SERVER_EXPLORER_CONTROL_BUDGET_V3\n\t\t// V3 actively sends login.init after LOGIN_OK. Let the native helper's own\n\t\t// post-login/read deadline expire naturally before the connector aborts it,\n\t\t// then leave a few seconds for INIT decoding and one bounded READONLY map probe.\n\t\tprobeCtx, cancel := context.WithTimeout(ctx, 30*time.Second)\n\t\tplayers, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)\n'''
    if s.count(old) != 1:
        raise SystemExit(f'SERVER_EXPLORER_CONTROL_BUDGET_ANCHOR expected 1 match, got {s.count(old)}')
    s = s.replace(old, new, 1)
    JOBS.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_CONTROL_BUDGET_V3=PATCHED')
print('SERVER_EXPLORER_CONTROL_BUDGET_SECONDS=30')
