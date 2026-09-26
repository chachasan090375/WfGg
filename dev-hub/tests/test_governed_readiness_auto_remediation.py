from __future__ import annotations
import importlib.util,json,tempfile,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))

def mod(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(module);return module

runtime=mod('runtime_adapter_registry',BIN/'runtime-adapter-registry.py')
auto=mod('domain_readiness_auto_remediator',BIN/'domain-readiness-auto-remediator.py')
router=mod('conversation_channel_router',BIN/'conversation-channel-router.py')

base=json.loads((ROOT/'dev-hub/config/provider-adapters.v1.json').read_text())
policy=json.loads((ROOT/'dev-hub/config/adapter-auto-remediation.v1.json').read_text())
provisioning=json.loads((ROOT/'dev-hub/config/adapter-provisioning.v1.json').read_text())

for adapter,provider in [('platform-command-adapter','chacha-tech-watch'),('context7-mcp-adapter','context7-mcp'),('architecture-specialist-adapter','chacha-dev-architect'),('collector-knowledge-adapter','collector-knowledge-runtime')]:
    ok,blockers,profile=auto.eligibility(adapter,provider,base,provisioning,policy)
    assert ok,(adapter,blockers)
    assert profile['automatic_external_spend_eur']==0

cloud=base['adapters']['cloudflare-pages-production-adapter']
assert set(cloud['supports']) & set(policy['production_permissions'])

with tempfile.TemporaryDirectory(prefix='runtime-adapter-registry-') as td:
    td=Path(td);exe=td/'adapter';exe.write_text('#!/bin/sh\nexit 0\n');exe.chmod(0o755)
    state=runtime.empty_state();adapter='platform-command-adapter'
    state['adapters'][adapter]={
      'adapter':adapter,'status':'ENABLED','executable':str(exe),'executable_digest':runtime.digest_file(exe),
      'contract_digest':runtime.contract_digest(base,adapter),'evidence_refs':['fixture'],'updated_at':runtime.now_iso(),
      'automatic_external_spend_eur':0}
    effective,report=runtime.reconcile(base,state)
    assert report['status']=='PASS',report
    assert effective['adapters'][adapter]['status']=='ENABLED'
    assert effective['adapters'][adapter]['executable']==str(exe)
    drift=json.loads(json.dumps(base));drift['adapters'][adapter]['supports'].append('repository-write')
    _,drift_report=runtime.reconcile(drift,state)
    row=next(x for x in drift_report['rows'] if x['adapter']==adapter)
    assert row['status']=='QUARANTINED' and 'CONTRACT_DIGEST_MISMATCH' in row['blockers'],row
    source_state=json.loads(json.dumps(state))
    source_state['adapters'][adapter]['source_version']=provisioning['adapters'][adapter]['version']
    source_state['adapters'][adapter]['source_digest']='sha256:'+'0'*64
    _,source_report=runtime.reconcile(base,source_state,ROOT/'dev-hub/config/provider-adapters.v1.json')
    source_row=next(x for x in source_report['rows'] if x['adapter']==adapter)
    assert source_row['status']=='QUARANTINED' and 'SOURCE_DIGEST_MISMATCH' in source_row['blockers'],source_row

# Legacy static ENABLED adapters are not silently reclassified by the runtime overlay reconciler.
# Source-drift quarantine applies to governed runtime overlay rows that carry provenance.
legacy=json.loads(json.dumps(base))
legacy['adapters']['collector-knowledge-adapter']['status']='ENABLED'
legacy['adapters']['collector-knowledge-adapter']['executable']='/opt/chacha-dev/adapters/collector-knowledge/current/collector-knowledge-adapter'
empty={'schema':'chacha.dev/runtime-adapter-state/v1','version':'1.0.0','adapters':{},'history':[],'automatic_external_spend_eur':0}
effective,legacy_report=runtime.reconcile(legacy,empty,ROOT/'dev-hub/config/provider-adapters.v1.json')
assert not any(x.get('adapter')=='collector-knowledge-adapter' for x in legacy_report['rows'])
assert effective['adapters']['collector-knowledge-adapter']['status']=='ENABLED'

assert router.route('CONVERSATION','Ne modifie rien, donne-moi le statut actuel','chacha-dev-platform')['subroute']=='ADVISORY'
assert router.route('CONVERSATION','Modifie le widget Android','chacha-dev-platform')['subroute']=='BUILD_HANDOFF_REQUIRED'

permissions=json.loads((ROOT/'dev-hub/config/domain-capability-permissions.v1.json').read_text())
assert permissions['overrides']['library-docs']=='read'
assert permissions['overrides']['technology-radar']=='read'
assert permissions['guardrails']['production_permission_never_inferred'] is True

central=(BIN/'central-interface-controller.py').read_text()
assert 'domain-factories-reconciled' in central
assert 'runtime-adapter-registry.py' in central
assert 'domain-readiness-auto-remediator.py' in central
assert 'provider_adapter_registry' in central

promotion=json.loads((ROOT/'dev-hub/config/adapter-promotion.v1.json').read_text())
principles=promotion['principles']
assert principles['blanket_automatic_promotion_forbidden'] is True
assert principles['governed_zero_spend_nonproduction_auto_remediation_allowed'] is True

print('CHACHA_DEV_GOVERNED_AUTO_REMEDIATION_POLICY=PASS')
print('CHACHA_DEV_RUNTIME_ADAPTER_OVERLAY=PASS')
print('CHACHA_DEV_RUNTIME_ADAPTER_CONTRACT_DRIFT_QUARANTINE=PASS')
print('CHACHA_DEV_RUNTIME_ADAPTER_SOURCE_DRIFT_QUARANTINE=PASS')
print('CHACHA_DEV_LEGACY_STATIC_ADAPTER_LIFECYCLE_PRESERVED=PASS')
print('CHACHA_DEV_DOMAIN_LEAST_PRIVILEGE_POLICY=PASS')
print('CHACHA_DEV_CONVERSATION_READ_ONLY_NEGATION=PASS')
print('CHACHA_DEV_AUTOMATIC_EXTERNAL_SPEND_EUR=0')
