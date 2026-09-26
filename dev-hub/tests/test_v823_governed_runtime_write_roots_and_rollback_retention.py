from __future__ import annotations
import importlib.util,json,os,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
UNIT=ROOT/'dev-hub/systemd/chacha-dev-direct-operator.service'
POLICY=ROOT/'dev-hub/config/direct-operator.v1.json'
CONSOLIDATION=ROOT/'dev-hub/config/platform-consolidation.v1.json'
PLANNER=ROOT/'dev-hub/bin/intendant-platform-consolidator.py'
CONTROLLER=ROOT/'dev-hub/bin/central-interface-controller.py'
REMEDIATOR=ROOT/'dev-hub/bin/domain-readiness-auto-remediator.py'

unit=UNIT.read_text(encoding='utf-8')
assert 'ProtectSystem=strict' in unit
line=next(x for x in unit.splitlines() if x.startswith('ReadWritePaths='))
roots=set(line.split('=',1)[1].split())
required={
 '/opt/chacha-dev/runtime/direct-operator','/opt/chacha-dev/runtime/human-interface',
 '/opt/chacha-dev/runtime/control','/opt/chacha-dev/runtime/progress',
 '/opt/chacha-dev/runtime/secrets/project-assurance','/opt/chacha-dev/runtime/adapter-auto-remediation',
 '/opt/chacha-dev/runtime/health','/opt/chacha-dev/runtime/registries',
 '/opt/chacha-dev/runtime/canonical-registry','/opt/chacha-dev/runtime/projects','/opt/chacha-dev/adapters'}
assert required <= roots,(required-roots)
assert '/opt/chacha-dev/runtime' not in roots
assert '/opt/chacha-dev' not in roots
assert 'ReadOnlyPaths=/opt/chacha-dev/runtime/secrets' in unit
policy=json.loads(POLICY.read_text())
assert policy['invariants']['governed_child_runtime_writes_are_explicitly_scoped'] is True
assert policy['invariants']['broad_runtime_write_root_forbidden'] is True
assert policy['invariants']['automatic_external_spend_eur']==0
controller=CONTROLLER.read_text();remediator=REMEDIATOR.read_text()
assert '"ADAPTER_ENABLEMENT_REQUIRED","PROVIDER_HEALTH_PROBE_REQUIRED"' in controller
for marker in ["runtime/'adapter-auto-remediation'","runtime/'registries/provider-adapter-runtime-state.v1.json'","runtime/'canonical-registry/dynamic-components.json'"]:
    assert marker in remediator,marker
print('CHACHA_DEV_V823_DIRECT_OPERATOR_GOVERNED_WRITE_ROOTS=PASS')
print('CHACHA_DEV_V823_BROAD_RUNTIME_WRITE_ROOT=FORBIDDEN')
print('CHACHA_DEV_V823_AUTOMATIC_EXTERNAL_SPEND_EUR=0')

spec=importlib.util.spec_from_file_location('planner',PLANNER)
planner=importlib.util.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(planner)
with tempfile.TemporaryDirectory(prefix='v823-strong-install-') as td:
    runtime=Path(td);nested=runtime/'release-gates'/'nested';nested.mkdir(parents=True)
    rev='9'*40
    (nested/'v821-install-pass.json').write_text(json.dumps({
      'schema':'chacha.dev/platform-install-pass/v1','status':'PASS','revision':rev,
      'direct_operator_health':'PASS','guardian_realtime':'PASS','installed_at':'2026-09-26T00:00:00Z'})+'\n')
    ranks=planner.strong_installed_revision_ranks(runtime)
    assert rev in ranks and ranks[rev]>0,ranks
print('CHACHA_DEV_V823_NESTED_INSTALL_EVIDENCE_DISCOVERY=PASS')
with tempfile.TemporaryDirectory(prefix='v823-retention-') as td:
    base=Path(td);platform=base/'platform';releases=platform/'releases';evidence=base/'evidence';runtime=base/'runtime'
    releases.mkdir(parents=True);evidence.mkdir();runtime.mkdir()
    revs={'old':'d'*40,'recent':'c'*40,'declared':'b'*40,'active':'a'*40}
    dirs={}
    for idx,key in enumerate(['old','recent','declared','active'],1):
        d=releases/(f'20260926T00000{idx}Z-'+revs[key]);d.mkdir();dirs[key]=d
        (d/'.revision').write_text(revs[key]+'\n')
        prep={'schema':'chacha.dev/release-preparation/v1','version':'8.2.'+str(idx),'revision':revs[key]}
        if key=='active':prep['rollback_revision']=revs['declared']
        (d/'.release-preparation.json').write_text(json.dumps(prep)+'\n')
        os.utime(d,(1000+idx,1000+idx))
        (evidence/(key+'.json')).write_text(json.dumps({'revision':revs[key],'observed_at':f'2026-09-26T00:00:0{idx}Z'})+'\n')
    (platform/'current').symlink_to(dirs['active'])
    cfg=json.loads(CONSOLIDATION.read_text())
    cfg['physical_release_retention']['runtime_evidence_root']=str(runtime)
    plan=planner.build_plan(platform,cfg,evidence)
    assert plan['declared_rollback_revision']==revs['declared'],plan
    assert plan['declared_rollback_protected'] is True,plan
    assert plan['selected_rollback_revisions'][0]==revs['declared'],plan['selected_rollback_revisions']
    byrev={r['revision']:r for r in plan['rows']}
    assert byrev[revs['declared']]['action']=='KEEP' and byrev[revs['declared']]['reason']=='DECLARED_ROLLBACK',byrev[revs['declared']]
    assert byrev[revs['active']]['action']=='KEEP',byrev[revs['active']]
    assert plan['retire_count']==1,plan
print('CHACHA_DEV_V823_DECLARED_ROLLBACK_RETENTION=PASS')
