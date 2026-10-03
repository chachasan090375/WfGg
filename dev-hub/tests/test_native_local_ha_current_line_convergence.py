#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
B=json.loads((ROOT/'dev-hub/config/native-local-current-line.birth.v1.json').read_text())
M=json.loads((ROOT/'dev-hub/config/master-roadmap.v1.json').read_text())
N=json.loads((ROOT/'dev-hub/evidence/native-local-resource-admission-current-vps-2026-10-03.json').read_text())
H=json.loads((ROOT/'dev-hub/evidence/ha-current-production-rehearsal-2026-10-03.json').read_text())
R=json.loads((ROOT/'dev-hub/evidence/native-local-current-runtime-state-2026-10-03.json').read_text())
assert B['production_activation_authorized'] is False
assert B['runtime_materialized'] is False and B['model_materialized'] is False
assert B['owner_foundry']=='branch-foundry'
assert N['status']=='PASS' and N['production_activation_authorized'] is False
assert R['service_active']=='inactive' and R['current_link_present'] is False and R['llama_server_present'] is False and R['model_artifact_present'] is False
assert H['status']=='BLOCK' and H['blockers']==['PLATFORM_REVISION_MISMATCH']
assert H['writer_switch_performed'] is False and H['failover_performed'] is False
work={x['id']:x for x in M['workstreams']}
assert work['provider-independence-native-local']['state']=='SOURCE_CONVERGED_RESOURCE_ADMISSION_PASS_RUNTIME_UNMATERIALIZED'
assert work['resilience-ha']['state']=='PROFILE_CONVERGED_CURRENT_PRODUCTION_READINESS_STALE_BLOCKED'
print('CHACHA_DEV_NATIVE_LOCAL_HA_CURRENT_LINE_CONVERGENCE=PASS')
print('NATIVE_LOCAL_ACTIVATION=NO')
print('HA_FAILOVER=NO')
print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
