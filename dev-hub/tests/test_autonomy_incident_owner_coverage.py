#!/usr/bin/env python3
import ast,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; BIN=ROOT/'dev-hub/bin'; CFG=ROOT/'dev-hub/config'
sys.path.insert(0,str(BIN))
def mod(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
asm=mod('asm_owner_coverage',BIN/'autonomy-self-model.py')
self_policy=json.loads((CFG/'autonomy-self-model.v1.json').read_text())
sup_policy=json.loads((CFG/'autonomy-supervision.v1.json').read_text())
tree=ast.parse((BIN/'component_registry_reconciler.py').read_text())
pairs=set()
for node in ast.walk(tree):
 if not (isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='issue' and len(node.args)>=4):continue
 code=node.args[0];action=node.args[3]
 if isinstance(code,ast.Constant) and isinstance(code.value,str) and isinstance(action,ast.Constant) and isinstance(action.value,str):pairs.add((code.value,action.value))
assert len(pairs)>=14,pairs
auto=[];human=[]
for code,action in sorted(pairs):
 row=asm.issue_view({'code':code,'severity':'HIGH','subject':'contract-test','recommended_action':action},self_policy)
 assert row['owner']!='UNRESOLVED',(code,action,row)
 assert row['class']!='UNKNOWN_DRIFT',(code,action,row)
 if row['class']=='HUMAN_BOUNDARY':
  human.append((code,action,row['owner']));continue
 if row['class']=='EXTERNAL_DEPENDENCY':continue
 spec=(sup_policy.get('owner_actions') or {}).get(row['recommended_action'])
 assert isinstance(spec,dict),(code,action,row)
 dispatch=spec.get('dispatch') or {}
 assert dispatch.get('type')=='systemd-unit' and dispatch.get('unit'),(code,action,spec)
 assert dispatch['unit'] in (sup_policy.get('runtime') or {}).get('allowed_systemd_units',[]),(code,action,dispatch)
 auto.append((code,row['recommended_action'],spec.get('owner')))
assert ('FLEET_MISSING','BACKFILL_FLEET_FROM_CANONICAL_REGISTRY','agent-fleet-observatory') in auto,auto
assert ('RELEASE_OVERAGE','RECONCILE_RELEASE_RETENTION','intendant') in auto,auto
assert any(x[0]=='ACTIVE_RELEASE_METADATA_DRIFT' and x[2]=='release-engineer' for x in human),human
assert any(x[0]=='VERSION_COUPLED_ACTIVE_LOGIC' and x[2]=='architecture-council' for x in human),human
print('CHACHA_DEV_AUTONOMY_INCIDENT_OWNER_COVERAGE=PASS')
print('DETECTED_ACTION_PAIRS='+str(len(pairs)))
print('AUTO_DISPATCHABLE='+str(len(auto)))
print('HUMAN_BOUNDARY='+str(len(human)))
print('AUTOMATIC_EXTERNAL_SPEND_EUR=0')
