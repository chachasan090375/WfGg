#!/usr/bin/env python3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
checks={
 'guardian-client.py':('sovereign_state_authority as ssa','ssa.endpoint("guardian")'),
 'sentinel-client.py':('sovereign_state_authority as ssa','ssa.endpoint("sentinel")'),
 'assurance-exchange-client.py':('sovereign_state_authority as ssa','ssa.endpoint("assurance-exchange")'),
 'central-learning-relay-puller.py':('sovereign_state_authority as ssa','ssa.endpoint("learning-relay")'),
 'cockpit-state.py':('sovereign_state_authority as ssa',"ssa.endpoint('guardian')","ssa.endpoint('sentinel')"),
}
for f,needles in checks.items():
 s=(ROOT/'dev-hub/bin'/f).read_text()
 for n in needles:assert n in s,(f,n)
# Runtime service must use release-bound puller so authority resolver changes atomically with platform releases.
u=(ROOT/'dev-hub/systemd/chacha-dev-central-learning-relay-pull.service').read_text()
assert '/opt/chacha-dev/platform/current/dev-hub/bin/central-learning-relay-puller.py' in u
# Historical installers and embedded remote probes may retain cloud endpoints, but core runtime clients may not bypass resolver.
for f in checks:
 s=(ROOT/'dev-hub/bin'/f).read_text()
 if f!='cockpit-state.py':
  assert 'workers.dev' not in '\n'.join(line for line in s.splitlines() if 'DEFAULT_' not in line),f
print('CHACHA_DEV_SOVEREIGN_STATE_RUNTIME_ROUTING=PASS')
print('CORE_RUNTIME_D1_DIRECT_BYPASS=NO')
