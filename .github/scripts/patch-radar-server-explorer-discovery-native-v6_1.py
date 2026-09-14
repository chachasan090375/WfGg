#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/native-template/main.go')

s = MAIN.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_DISCOVERY_NATIVE_V61'
if marker not in s:
    old = '''func parseServerBatchV6(raw string) ([]string, bool) {\n\tparts := strings.Split(raw, ",")\n\tif len(parts) == 0 || len(parts) > 12 {\n'''
    new = '''// SERVER_EXPLORER_DISCOVERY_NATIVE_V61\n// V6.1 raises the explicit single-session probe ceiling only for bounded\n// discovery. The connector limits discovery to a 47-server window.\nfunc parseServerBatchV6(raw string) ([]string, bool) {\n\tparts := strings.Split(raw, ",")\n\tif len(parts) == 0 || len(parts) > 48 {\n'''
    if s.count(old) != 1:
        raise SystemExit(f'V61_NATIVE_BATCH_ANCHOR expected 1 match, got {s.count(old)}')
    s = s.replace(old, new, 1)
    MAIN.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_DISCOVERY_NATIVE_V61=PATCHED')
print('SERVER_EXPLORER_V61_MAX_BATCH=48')
print('SERVER_EXPLORER_V61_DISCOVERY_WINDOW=47')
