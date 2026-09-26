from __future__ import annotations
import importlib.util,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/'dev-hub/bin'
sys.path.insert(0,str(BIN))

def loadmod(name:str,path:Path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);assert spec and spec.loader
    spec.loader.exec_module(mod);return mod

intent_mod=loadmod('v822_intent',BIN/'functional-intent-orchestrator.py')
run_mod=loadmod('v822_run',BIN/'run-controller.py')
cfg=json.loads((ROOT/'dev-hub/config/domain-orchestration.v1.json').read_text())

smoke='Crée une preuve BUILD locale minimale, sans déploiement production, sans accès réseau externe et sans dépense externe.'
plan=intent_mod._preplan({'text':smoke},cfg)
assert plan['primary_domains']==['platform-selftest'],plan['primary_domains']
assert plan['review_domains']==[],plan['review_domains']
assert plan['packages'][0]['capabilities']==['platform-selftest']
assert intent_mod.keyword_matches('déploie en production','production') is True
assert intent_mod.keyword_matches('sans déploiement production','production') is False
assert intent_mod.keyword_matches('preuve locale minimale','locale') is False
assert intent_mod.keyword_matches('traduction pour la locale fr-FR','locale') is True
registry=json.loads((ROOT/'dev-hub/config/capability-registry.v1.json').read_text())
providers=json.loads((ROOT/'dev-hub/config/provider-adapters.v1.json').read_text())
probes=json.loads((ROOT/'dev-hub/config/provider-health-probes.v1.json').read_text())
permissions=json.loads((ROOT/'dev-hub/config/domain-capability-permissions.v1.json').read_text())
auto=json.loads((ROOT/'dev-hub/config/adapter-auto-remediation.v1.json').read_text())
provisioning=json.loads((ROOT/'dev-hub/config/adapter-provisioning.v1.json').read_text())

cap=registry['capabilities']['platform-selftest']
assert cap['providers'][0]['id']=='platform-selftest-runtime'
assert providers['providers']['platform-selftest-runtime']['adapter']=='platform-selftest-adapter'
assert providers['adapters']['platform-selftest-adapter']['supports']==['read']
assert probes['providers']['platform-selftest-runtime']['functional_check']=='platform-revision-proof'
assert permissions['overrides']['platform-selftest']=='read'
ok,blockers,profile=loadmod('v822_auto',BIN/'domain-readiness-auto-remediator.py').eligibility(
    'platform-selftest-adapter','platform-selftest-runtime',providers,provisioning,auto)
assert ok,blockers
assert profile['automatic_external_spend_eur']==0

fixture=provisioning['adapters']['platform-selftest-adapter']['probe']['input']
proc=subprocess.run([sys.executable,str(ROOT/'dev-hub/adapters/platform-selftest-adapter.py')],
                    input=json.dumps(fixture),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
assert proc.returncode==0,proc.stderr
result=json.loads(proc.stdout)
assert result['status']=='OK' and result['producer']=='platform-selftest-adapter',result
run_policy=json.loads((ROOT/'dev-hub/config/run-controller.v1.json').read_text())
write_env={'project':'project-v822','task':{'permission':'workspace-write'},
           'workspace':'/opt/chacha-dev/runtime/projects/project-v822/branches/development'}
assert run_mod.workspace_blockers(write_env,run_policy)==[]
assert run_mod.workspace_blockers({'project':'project-v822','task':{'permission':'workspace-write'},'workspace':None},run_policy)==['WORKSPACE_REQUIRED_FOR_WRITE']
assert run_mod.workspace_blockers({'project':'project-v822','task':{'permission':'workspace-write'},'workspace':'/tmp/outside'},run_policy)==['WORKSPACE_OUTSIDE_GOVERNED_ROOT']
assert run_mod.workspace_blockers({'project':'project-v822','task':{'permission':'read'},'workspace':None},run_policy)==[]

factory=(BIN/'domain-factory-runner.py').read_text()
functional=(BIN/'functional-intent-orchestrator.py').read_text()
assert '"branch_workspace":pkg.get("workspace")' in factory
assert '"platform_selftest":{"action":"revision-proof"}' in factory
assert 'x["workspace"]=b.get("workspace")' in functional

print('CHACHA_DEV_V822_NEGATION_AWARE_DOMAIN_ROUTING=PASS')
print('CHACHA_DEV_V822_PLATFORM_SELFTEST_LANE=PASS')
print('CHACHA_DEV_V822_BRANCH_WORKSPACE_PROPAGATION=PASS')
print('CHACHA_DEV_V822_AUTOMATIC_EXTERNAL_SPEND_EUR=0')

button='Ajoute un bouton STOP dans le widget Android et teste que le bouton fonctionne.'
button_plan=intent_mod._preplan({'text':button},cfg)
assert button_plan['primary_domains']==['development','ui-layout'],button_plan['primary_domains']
assert set(button_plan['review_domains'])=={'qa','cybersecurity'},button_plan['review_domains']
by_id={p['id']:p['capabilities'] for p in button_plan['packages']}
assert by_id['domain:development']==['code-edit'],by_id
assert by_id['review:qa']==['test-strategy'],by_id
assert by_id['review:cybersecurity']==['threat-model','secrets-review','dependency-review'],by_id
code_providers=registry['capabilities']['code-edit']['providers']
assert [p['id'] for p in code_providers]==['antigravity'],code_providers
print('CHACHA_DEV_V822_INTENT_SCOPED_CAPABILITIES=PASS')
print('CHACHA_DEV_V822_GENERATIVE_PROVIDER_ECONOMICS_FAIL_CLOSED=PASS')
ag_fixture=provisioning['adapters']['antigravity-adapter']['probe']['input']
ag_proc=subprocess.run([sys.executable,str(ROOT/'dev-hub/adapters/antigravity-adapter.py')],
                       input=json.dumps(ag_fixture),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
ag_result=json.loads(ag_proc.stdout)
assert ag_proc.returncode==2,(ag_proc.returncode,ag_result,ag_proc.stderr)
assert ag_result['status']=='BLOCKED' and ag_result['summary']=='ZERO_COST_ATTESTATION_MISSING',ag_result
assert ag_result['evidence'][0]['details']['provider_invocation_started'] is False
print('CHACHA_DEV_V822_ANTIGRAVITY_NO_ATTESTATION_NO_INVOCATION=PASS')
