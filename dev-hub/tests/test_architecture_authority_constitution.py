from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
load=lambda p: json.loads((ROOT/p).read_text(encoding='utf-8'))
policy=load('dev-hub/config/architecture-decision-council.v1.json')
uncert=load('dev-hub/config/uncertainty-policy.v1.json')
roles=load('dev-hub/config/guardian-role-contracts.v1.json')
road=load('dev-hub/config/autonomy-roadmap-evolution-routing.v1.json')
assert policy['central_orchestrator_is_final_decider'] is False
assert policy['architecture_council_is_advisory'] is True
assert policy['revalidated_reuse_may_dispatch_without_human'] is True
assert policy['new_architecture_synthesis_requires_human_approval'] is True
assert policy['material_architecture_change_requires_human_approval'] is True
assert uncert['ask_human_only_if']['new_architecture_synthesis_or_material_architecture_change'] is True
assert 'reversible-architecture-choice' not in uncert['never_ask_human_for']
byid={x['contract_id']:x for x in roles['contracts']}
for cid in ('component:central-orchestrator','role:architecture-decision-council'):
    c=byid[cid]
    assert 'FINAL_ARCHITECTURE_DECISION' not in c['allowed_actions'],c
    assert 'FINAL_ARCHITECTURE_DECISION' in c['forbidden_actions'],c
    assert 'REPORT_ARCHITECTURE_RECOMMENDATION' in c['allowed_actions'],c
assert road['principles']['architecture_council_final_authority'] is False
assert road['principles']['architecture_council_recommendation_authority'] is True
orch=(ROOT/'dev-hub/bin/autonomous-project-orchestrator.py').read_text(encoding='utf-8')
assert 'action="FINAL_ARCHITECTURE_DECISION"' not in orch
assert 'action="REPORT_ARCHITECTURE_RECOMMENDATION"' in orch
print('CHACHA_DEV_ARCHITECTURE_AUTHORITY_CONSTITUTION=PASS')

import importlib.util
spec=importlib.util.spec_from_file_location("adc",ROOT/"dev-hub/bin/architecture-decision-council.py")
adc=importlib.util.module_from_spec(spec);spec.loader.exec_module(adc)
reuse=adc.architecture_authority("REUSE_REVALIDATED_BRANCH",[])
assert reuse["decision_authority"]=="ADVISORY" and reuse["dispatch_allowed"] is True and reuse["human_approval_required"] is False,reuse
new=adc.architecture_authority("FOUNDRY_SYNTHESIS",[])
assert new["recommendation_ready"] is True and new["dispatch_allowed"] is False and new["human_approval_required"] is True,new
blocked=adc.architecture_authority("REUSE_REVALIDATED_BRANCH",["constraint-policy"])
assert blocked["recommendation_ready"] is False and blocked["dispatch_allowed"] is False,blocked
print("CHACHA_DEV_ARCHITECTURE_AUTHORITY_BEHAVIOR=PASS")
