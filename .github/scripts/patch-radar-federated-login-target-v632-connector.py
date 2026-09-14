#!/usr/bin/env python3
from pathlib import Path

REGION = Path('/tmp/wfgg-radar/connector-go/internal/protocol/region_scan.go')
s = REGION.read_text(encoding='utf-8')
marker = 'FEDERATED_COLLECTOR_V632_LOGIN_ENV'
if marker in s:
    print('FEDERATED_COLLECTOR_V632_LOGIN_ENV=ALREADY_PRESENT')
    raise SystemExit(0)

old = '''\t\tif federatedMapOnly {\n\t\t\tenv = append(env, "WFGG_FEDERATED_MAP_ONLY=1")\n\t\t\tif region != nil {\n'''
new = '''\t\tif federatedMapOnly {\n\t\t\t// FEDERATED_COLLECTOR_V632_LOGIN_ENV\n\t\t\t// Unlike Server Explorer probes, a federated scan must target the zone\n\t\t\t// during login so serverInfo redirect can establish the real shard session.\n\t\t\tenv = append(env, "WFGG_FEDERATED_MAP_ONLY=1", "WFGG_LOGIN_SERVER_ID_OVERRIDE="+serverIDOverride)\n\t\t\tif region != nil {\n'''
if s.count(old) != 1:
    raise SystemExit(f'FEDERATED_V632_CONNECTOR_ANCHOR_EXPECTED_1_GOT_{s.count(old)}')
s = s.replace(old, new, 1)
REGION.write_text(s, encoding='utf-8')
print('FEDERATED_COLLECTOR_V632_LOGIN_ENV=PATCHED')
print('FEDERATED_COLLECTOR_V632_SERVER_EXPLORER_PROBE=UNCHANGED')
