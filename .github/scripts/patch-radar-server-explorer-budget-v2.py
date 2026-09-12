#!/usr/bin/env python3
from pathlib import Path

JOBS = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')

s = JOBS.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_CONTROL_BUDGET_V4'
if marker not in s:
    old = '''\t\tprobeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)\n\t\tplayers, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)\n'''
    new = '''\t\t// SERVER_EXPLORER_CONTROL_BUDGET_V4\n\t\t// V4 mirrors the reference init bootstrap: up to 45s after LOGIN_OK, with\n\t\t// login.init sent halfway through. The outer connector budget must exceed\n\t\t// that native window plus dial/login overhead so Sentinel sees the native\n\t\t// verdict instead of killing the process first.\n\t\tprobeCtx, cancel := context.WithTimeout(ctx, 60*time.Second)\n\t\tplayers, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)\n'''
    if s.count(old) != 1:
        raise SystemExit(f'SERVER_EXPLORER_CONTROL_BUDGET_ANCHOR expected 1 match, got {s.count(old)}')
    s = s.replace(old, new, 1)
    JOBS.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_CONTROL_BUDGET_V4=PATCHED')
print('SERVER_EXPLORER_CONTROL_BUDGET_SECONDS=60')
