#!/usr/bin/env python3
import fnmatch,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];CFG=ROOT/'dev-hub/config';BIN=ROOT/'dev-hub/bin'
def load(n):return json.load(open(CFG/n))
policy=load('platform-promotion-transaction.v1.json')
assert policy['invariants']['single_active_promotion_writer'] is True
assert policy['invariants']['receipt_write_once'] is True
assert policy['invariants']['ledger_append_only'] is True
assert policy['invariants']['expired_active_base_promotion_may_be_superseded_only_by_exact_approved_successor'] is True
assert policy['invariants']['superseding_expired_active_base_must_not_mutate_current_or_delete_release'] is True
assert policy['invariants']['current_release_switch_only_via_governed_platform_promotion'] is True
assert policy['exclusive_writer']['component_id']=='governed-platform-promotion'
print('CHACHA_DEV_PROMOTION_TRANSACTION_POLICY=PASS')

ops=load('operator-directives.v1.json');d=next(x for x in ops['directives'] if x['directive_id']=='opdir-platform-promotion-single-writer')
assert d['status']=='ACTIVE' and d['scope']=='PLATFORM_GLOBAL' and d['backfill_required'] is True
sinks=load('operator-directive-sinks.v1.json')['sinks'];assert all(x in sinks for x in d['required_sinks'])
print('CHACHA_DEV_PROMOTION_OPERATOR_DIRECTIVE_PROPAGATION=PASS')

reg=load('canonical-component-registry.v1.json');gate=reg['promotion_gate']
assert gate['single_writer_lease_required'] is True and gate['immutable_receipts_required'] is True
assert gate['exclusive_current_writer']=='governed-platform-promotion'
guard=load('guardian-role-contracts.v1.json')
for cid in ('component:governed-platform-promotion','role:governed-platform-promotion'):
 c=next(x for x in guard['contracts'] if x['contract_id']==cid)
 assert 'ACTIVATE_PLATFORM_RELEASE' in c['allowed_actions'] and 'ROLLBACK_PLATFORM_RELEASE' in c['allowed_actions']
 assert 'SUPERSEDE_EXPIRED_PLATFORM_PROMOTION' in c['allowed_actions']
 assert 'production-deploy' in c['allowed_permissions'] and 'OVERWRITE_PROMOTION_RECEIPT' in c['forbidden_actions']
 assert 'single_writer_promotion_lease' in c['required_evidence']
print('CHACHA_DEV_PROMOTION_GUARDIAN_CONTRACT=PASS')

sent=load('sentinel-technical-policy.v1.json')
assert 'promotion-single-writer-immutable-receipts' in sent['blocking_checks']
assert any(x['path']=='dev-hub/tests/test_autonomy_governed_platform_promotion.py' for x in sent['mandatory_platform_tests'])
life=load('lifecycle.v1.json')['platform_promotion_transaction'];assert life['receipt_mutability']=='WRITE_ONCE' and life['ledger']=='APPEND_ONLY'
intend=load('intendant-hygiene-cycle.v1.json')['invariants'];assert intend['promotion_lease_blocks_release_retirement'] is True
print('CHACHA_DEV_PROMOTION_SENTINEL_LIFECYCLE_INTENDANT=PASS')

for path,markers in {
 BIN/'release_state_reconciler.py':['PROMOTION_TRANSACTION_BLOCKS_RECONCILIATION'],
 BIN/'guardian-governed-release-state-reconciler.py':['PROMOTION_TRANSACTION_BLOCKS_RECONCILIATION'],
 BIN/'cockpit-state.py':['promotion_transaction'],
 BIN/'intendant-hygiene-cycle.py':['PROMOTION_TRANSACTION_PROTECTION'],
 BIN/'central-platform-hygiene-executor.py':['PROMOTION_TRANSACTION_PROTECTS_RELEASES'],
}.items():
 s=path.read_text();assert all(m in s for m in markers),(path,markers)
print('CHACHA_DEV_PROMOTION_BACKFILL_SURFACES=PASS')

# Classify every repo-local writer of /opt/chacha-dev/platform/current.
def mutates_current(p:Path)->bool:
 s=p.read_text(errors='ignore')
 if p.name=='governed-platform-promotion.py':return 'atomic_current_switch' in s and 'os.symlink' in s
 platform_current='/opt/chacha-dev/platform' in s
 return platform_current and any('ln -s' in line and 'CURRENT' in line for line in s.splitlines())
writers=[]
for p in sorted(BIN.iterdir()):
 if p.is_file() and mutates_current(p):writers.append(p)
patterns=policy['existing_writer_audit']['SUPERSEDED_PATTERNS'];unclassified=[];classes={}
for p in writers:
 rel=p.relative_to(ROOT).as_posix()
 if p.name=='governed-platform-promotion.py':classes[rel]='COMPLIANT'
 elif any(fnmatch.fnmatch(rel,pat) for pat in patterns):classes[rel]='SUPERSEDED'
 else:unclassified.append(rel)
assert not unclassified,unclassified
assert classes.get('dev-hub/bin/governed-platform-promotion.py')=='COMPLIANT'
assert any(v=='SUPERSEDED' for v in classes.values()),classes
print('CHACHA_DEV_PROMOTION_EXISTING_WRITER_CLASSIFICATION=PASS')
# Modern Run Controller executes only registered adapter executables. No registered executable may point to a superseded writer.
import json as _json
bad_exec=[]
def walk(v,path=''):
 if isinstance(v,dict):
  for k,x in v.items():
   np=(path+'.'+k).strip('.')
   if k=='executable' and isinstance(x,str) and ('install-' in x or 'run-v64-runtime-pilot-via-chacha-dev.sh' in x):bad_exec.append((np,x))
   walk(x,np)
 elif isinstance(v,list):
  for i,x in enumerate(v):walk(x,f'{path}[{i}]')
for cp in CFG.glob('*.json'):
 try:walk(_json.load(open(cp)),cp.name)
 except Exception:pass
# The audit policy itself contains glob names but not executable registrations.
assert not bad_exec,bad_exec
print('CHACHA_DEV_PROMOTION_SUPERSEDED_WRITERS_NOT_REGISTERED_FOR_EXECUTION=PASS')
print('COMPLIANT_WRITERS='+str(sum(v=='COMPLIANT' for v in classes.values())))
print('SUPERSEDED_WRITERS='+str(sum(v=='SUPERSEDED' for v in classes.values())))
print('UNCLASSIFIED_WRITERS=0')
print('CHACHA_DEV_PLATFORM_PROMOTION_SINGLE_WRITER_INVARIANT=PASS')
