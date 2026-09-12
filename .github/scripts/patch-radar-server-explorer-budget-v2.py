#!/usr/bin/env python3
from pathlib import Path

JOBS = Path('/tmp/wfgg-radar/connector-go/cmd/radar-connector/collector_jobs.go')

s = JOBS.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_CONTROL_BUDGET_V2'
if marker not in s:
    old = '''\t\tprobeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)\n\t\tplayers, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)\n'''
    new = '''\t\t// SERVER_EXPLORER_CONTROL_BUDGET_V2\n\t\t// Sentinel proved that the native session reaches LOGIN_OK at ~5s and is\n\t\t// still waiting for INIT. Give the control probe enough time to complete\n\t\t// INIT and dispatch one bounded READONLY world.get.block request.\n\t\tprobeCtx, cancel := context.WithTimeout(ctx, 15*time.Second)\n\t\tplayers, probeErr := scanner.ScanPlayerServerRegion(probeCtx, token, "*", sid, 0)\n'''
    if s.count(old) != 1:
        raise SystemExit(f'SERVER_EXPLORER_CONTROL_BUDGET_ANCHOR expected 1 match, got {s.count(old)}')
    s = s.replace(old, new, 1)
    JOBS.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_CONTROL_BUDGET_V2=PATCHED')
print('SERVER_EXPLORER_CONTROL_BUDGET_SECONDS=15')
