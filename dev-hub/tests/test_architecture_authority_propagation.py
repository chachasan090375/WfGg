#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
# Current config may preserve the legacy field name for compatibility, but never with final authority=true.
violations=[]
for p in sorted((ROOT/'dev-hub/config').glob('*.json')):
    x=json.loads(p.read_text(encoding='utf-8'))
    def walk(v,path=''):
        if isinstance(v,dict):
            if 'architecture_council_final_authority' in v:
                if v['architecture_council_final_authority'] is not False:
                    violations.append(f'{p}:{path}:FINAL_NOT_FALSE')
                if v.get('architecture_council_recommendation_authority') is not True:
                    violations.append(f'{p}:{path}:RECOMMENDATION_NOT_TRUE')
            if 'architecture_council_final_authority_preserved' in v:
                if v['architecture_council_final_authority_preserved'] is not False:
                    violations.append(f'{p}:{path}:PRESERVED_FINAL_NOT_FALSE')
                if v.get('architecture_council_recommendation_authority_preserved') is not True:
                    violations.append(f'{p}:{path}:PRESERVED_RECOMMENDATION_NOT_TRUE')
            for k,z in v.items(): walk(z,path+'.'+k if path else k)
        elif isinstance(v,list):
            for i,z in enumerate(v): walk(z,f'{path}[{i}]')
    walk(x)
# Executable current source (historical install scripts excluded) must not emit/require final=true.
for p in sorted((ROOT/'dev-hub/bin').iterdir()):
    if not p.is_file() or p.name.startswith('install-') or p.suffix not in {'.py','.mjs','.sh'}: continue
    s=p.read_text(encoding='utf-8')
    if re.search(r'architecture_council_final_authority["\']?\s*[:=]\s*True\b',s):
        violations.append(f'{p}:EMITS_FINAL_TRUE')
    if re.search(r'get\(["\']architecture_council_final_authority["\']\)\s+is\s+True',s):
        violations.append(f'{p}:REQUIRES_FINAL_TRUE')
assert not violations,violations
# Canonical authority policies must be explicit.
g=json.loads((ROOT/'dev-hub/config/guardian-role-contracts.v1.json').read_text())['principles']
c=json.loads((ROOT/'dev-hub/config/architecture-decision-council.v1.json').read_text())
r=json.loads((ROOT/'dev-hub/config/autonomy-roadmap-evolution-routing.v1.json').read_text())['principles']
assert g['architecture_council_is_advisory'] is True
assert g['central_orchestrator_cannot_self_authorize_architecture'] is True
assert c['central_orchestrator_is_final_decider'] is False
assert c['new_architecture_synthesis_requires_human_approval'] is True
assert r['architecture_council_final_authority'] is False
assert r['architecture_council_recommendation_authority'] is True
print('CHACHA_DEV_ARCHITECTURE_AUTHORITY_PROPAGATION=PASS')
print('CHACHA_DEV_ARCHITECTURE_COUNCIL_FINAL_AUTHORITY=NO')
print('CHACHA_DEV_ARCHITECTURE_COUNCIL_RECOMMENDATION_AUTHORITY=YES')
