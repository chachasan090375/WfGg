from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UNIT=ROOT/'dev-hub/systemd/chacha-dev-direct-operator.service'
DIRECT=ROOT/'dev-hub/config/direct-operator.v1.json'
PROJECT=ROOT/'dev-hub/config/project-control.v1.json'
RUN=ROOT/'dev-hub/config/run-controller.v1.json'
DOWNSTREAM=ROOT/'dev-hub/config/direct-operator-downstream-runtime-writes.v1.json'
ARCH=ROOT/'dev-hub/adapters/architecture-specialist-adapter.py'

def covered(path:str, roots:set[str])->bool:
    p=Path(path)
    return any(p==Path(root) or Path(root) in p.parents for root in roots)

unit=UNIT.read_text(encoding='utf-8')
assert 'ProtectSystem=strict' in unit
line=next(x for x in unit.splitlines() if x.startswith('ReadWritePaths='))
roots=set(line.split('=',1)[1].split())
assert '/opt/chacha-dev/runtime' not in roots
assert '/opt/chacha-dev' not in roots
assert 'ReadOnlyPaths=/opt/chacha-dev/runtime/secrets' in unit
assert '/opt/chacha-dev/runtime/secrets' not in roots
assert '/opt/chacha-dev/runtime/secrets/project-assurance' in roots

direct=json.loads(DIRECT.read_text())
project=json.loads(PROJECT.read_text())
run=json.loads(RUN.read_text())
downstream=json.loads(DOWNSTREAM.read_text())
inv=direct['invariants']
for key in [
 'governed_child_runtime_writes_are_explicitly_scoped',
 'governed_build_runtime_roots_derive_from_child_runtime_contracts',
 'project_control_runtime_roots_must_be_systemd_write_scoped',
 'run_controller_runtime_roots_must_be_systemd_write_scoped',
 'operator_directive_runtime_root_must_be_systemd_write_scoped',
 'downstream_child_runtime_write_contract_required',
 'downstream_child_processes_inherit_service_sandbox',
 'broad_runtime_write_root_forbidden']:
    assert inv[key] is True,key
assert inv['automatic_external_spend_eur']==0

project_roots=set(str(v) for v in project['runtime'].values())
for required in project_roots:
    assert required.startswith('/opt/chacha-dev/runtime/'),required
    assert covered(required,roots),(required,sorted(roots))
print('CHACHA_DEV_V824_PROJECT_CONTROL_RUNTIME_ROOTS_SCOPED=PASS')

run_roots={str(run['locking']['root']),str(run['dispatch']['work_root']),str(run['workspace']['root'])}
for required in run_roots:
    assert required.startswith('/opt/chacha-dev/runtime/'),required
    assert covered(required,roots),(required,sorted(roots))
print('CHACHA_DEV_V824_RUN_CONTROLLER_RUNTIME_ROOTS_SCOPED=PASS')

intake=Path(str(direct['operator_directives']['intake']))
directive_root=str(intake.parent)
assert directive_root.startswith('/opt/chacha-dev/runtime/'),directive_root
assert covered(directive_root,roots),(directive_root,sorted(roots))
print('CHACHA_DEV_V824_STRUCTURAL_OPERATOR_DIRECTIVE_ROOT_SCOPED=PASS')
print('CHACHA_DEV_V824_BROAD_RUNTIME_WRITE_ROOT=FORBIDDEN')
print('CHACHA_DEV_V824_AUTOMATIC_EXTERNAL_SPEND_EUR=0')

assert direct['downstream_runtime_write_contract']=='dev-hub/config/direct-operator-downstream-runtime-writes.v1.json'
assert downstream['principles']['child_processes_inherit_direct_operator_filesystem_sandbox'] is True
assert downstream['principles']['every_downstream_runtime_write_root_must_be_declared'] is True
assert downstream['principles']['broad_runtime_write_root_forbidden'] is True
assert downstream['automatic_external_spend_eur']==0
for owner,declared in downstream['roots'].items():
    for required in declared:
        assert required.startswith('/opt/chacha-dev/runtime/'),(owner,required)
        assert required!='/opt/chacha-dev/runtime',(owner,required)
        assert covered(required,roots),(owner,required,sorted(roots))
print('CHACHA_DEV_V824_DOWNSTREAM_CHILD_RUNTIME_ROOTS_SCOPED=PASS')

import importlib.util
spec=importlib.util.spec_from_file_location('v824_arch',ARCH)
arch=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(arch)
request={
 'schema':'chacha.dev/dispatch-envelope/v1','project':'fixture','run_id':'run-fixture',
 'task':{'id':'capability:domain-qa:test-strategy','owner_role':'test-engineer+performance-engineer','permission':'plan','capabilities':['test-strategy'],'outputs':[]},
 'bindings':[{'provider':'chacha-dev-architect','adapter':'architecture-specialist-adapter','health_state':'HEALTHY'}],
 'metadata':{'execution_mode':'DIRECT_PROVIDER','domain':'qa','package_id':'domain:qa','intent_excerpt':'Créer un artefact de diagnostic interne sans déploiement.'}
}
action,data,error=arch.validate_request(request)
assert error is None,(action,error)
assert action=='design' and data['generic_domain']['capability']=='test-strategy',data
no_intent=json.loads(json.dumps(request));no_intent['metadata']['intent_excerpt']=''
_,_,error=arch.validate_request(no_intent);assert error=='TECHNICAL_DESIGN_CONTEXT_MISSING',error
wrong_mode=json.loads(json.dumps(request));wrong_mode['metadata']['execution_mode']='TECHNICAL_DESIGN'
_,_,error=arch.validate_request(wrong_mode);assert error=='TECHNICAL_DESIGN_CONTEXT_MISSING',error
print('CHACHA_DEV_V824_GENERIC_DOMAIN_PLAN_CAPABILITY=PASS')

ORCH=ROOT/'dev-hub/bin/functional-intent-orchestrator.py'
FACTORY=ROOT/'dev-hub/bin/domain-factory-runner.py'
AUTO=ROOT/'dev-hub/bin/domain-readiness-auto-remediator.py'
import importlib.util as _iu
def _load(name,path):
    spec=_iu.spec_from_file_location(name,path);m=_iu.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(m);return m
orch=_load('v824_orch',ORCH);factory=_load('v824_factory',FACTORY);auto=_load('v824_auto',AUTO)
intent='Crée un artefact de diagnostic interne minimal pour vérifier le chemin BUILD de ChaCha DEV : un fichier status.txt contenant uniquement BUILD_PATH_OK dans un espace de projet de test. Aucun déploiement, aucun secret, aucune dépendance externe, aucune dépense, aucune modification de production.'
cfg=json.loads((ROOT/'dev-hub/config/domain-orchestration.v1.json').read_text())
primary,reasons=orch.match_domains(orch.normalize(intent),cfg,[])
assert 'workspace-artifact' in primary,(primary,reasons)
ws=cfg['domains']['workspace-artifact'];assert orch.routed_capabilities(intent,ws,'primary')==['workspace-file-write']
assert factory.workspace_file_spec(intent)=={'action':'write-text','path':'status.txt','content':'BUILD_PATH_OK'}
cap=json.loads((ROOT/'dev-hub/config/capability-registry.v1.json').read_text())['capabilities']['workspace-file-write']
assert cap['class']=='execution' and cap['providers'][0]['id']=='workspace-file-runtime'
reg=json.loads((ROOT/'dev-hub/config/provider-adapters.v1.json').read_text())
prov=json.loads((ROOT/'dev-hub/config/adapter-provisioning.v1.json').read_text())
pol=json.loads((ROOT/'dev-hub/config/adapter-auto-remediation.v1.json').read_text())
ok,blockers,profile=auto.eligibility('workspace-file-adapter','workspace-file-runtime',reg,prov,pol)
assert ok,(blockers,profile)
assert set(reg['adapters']['workspace-file-adapter']['supports'])=={'read','workspace-write'}
assert not (set(reg['adapters']['workspace-file-adapter']['supports']) & set(pol['production_permissions']))
assert prov['adapters']['architecture-specialist-adapter']['version']=='1.0.7'
print('CHACHA_DEV_V824_WORKSPACE_ARTIFACT_ROUTING=PASS')
print('CHACHA_DEV_V824_WORKSPACE_FILE_AUTO_REMEDIATION_ELIGIBLE=PASS')
print('CHACHA_DEV_V824_ARCHITECTURE_ADAPTER_SOURCE_VERSION_107=PASS')

sync=(ROOT/'.github/workflows/dev-hub-v7-guardian-contract-sync.yml').read_text()
assert "name: ChaCha DEV Guardian contract sync" in sync
assert "- 'production-guardian-contract-sync-v*'" in sync
assert "- 'dev-hub-v*'" not in sync
assert 'workflow_dispatch:' in sync
assert "dev-hub/config/provider-adapters.v1.json" in sync
assert "'contract_id':'adapter:'+adapter_id" in sync
assert "WHERE role_contracts.source_digest<>excluded.source_digest" in sync
assert "CHACHA_DEV_GUARDIAN_ADAPTER_CONTRACT_SYNC=PASS" in sync
print('CHACHA_DEV_V824_GUARDIAN_ADAPTER_CONTRACT_SYNC=PASS')
print('CHACHA_DEV_V824_GUARDIAN_D1_DEV_BRANCH_MUTATION=FORBIDDEN')

central=(ROOT/'dev-hub/bin/central-interface-controller-core.py').read_text()
for marker in ['def verify_domain_run_results','"verify-result"','DOMAIN_EXECUTION_VERIFICATION_REQUIRED','"domain_execution_verified"','status="COMPLETE";next_action="AWAIT_NEW_INSTRUCTION"','continuation_mode":"DOMAIN_EXECUTION_VERIFICATION_RESUME"']:
    assert marker in central,marker
print('CHACHA_DEV_V824_INDEPENDENT_RESULT_VERIFICATION_GATE=PASS')
print('CHACHA_DEV_V824_VERIFIED_EXECUTION_TERMINATES=PASS')

sync=(ROOT/'.github/workflows/dev-hub-v7-guardian-contract-sync.yml').read_text()
for marker in [
    'confirm_production:',
    'guardian-contracts-production',
    'approved_by',
    'Checkout exact approved contract source revision',
    'git checkout --detach',
    "DELETE FROM role_contracts WHERE kind='adapter'",
    'CHACHA_DEV_GUARDIAN_ADAPTER_CONTRACT_SET_RECONCILIATION=PASS',
    'CHACHA_DEV_GUARDIAN_ADAPTER_CONTRACT_READBACK=PASS',
]:
    assert marker in sync,marker
print('CHACHA_DEV_V824_GUARDIAN_CONTRACT_SYNC_HUMAN_BOUNDARY=PASS')
print('CHACHA_DEV_V824_GUARDIAN_CONTRACT_SYNC_EXACT_REVISION=PASS')
print('CHACHA_DEV_V824_GUARDIAN_CONTRACT_ROLLBACK_RECONCILIATION=PASS')
